#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_ROOT="${SCISCOPE_ROOT:-/home/liu/workspaces/sciscope}"
SCISCOPE_REPO="${SCISCOPE_REPO:-${SCISCOPE_ROOT}/repo}"
RUNTIME_DIR="${SCISCOPE_ROOT}/runtime"
DB_ENV_FILE="${RUNTIME_DIR}/postgres.env"
PGPASS_FILE="${RUNTIME_DIR}/.pgpass"

if [[ ! -d "${SCISCOPE_REPO}/.git" ]]; then
  echo "Expected SciScope checkout at ${SCISCOPE_REPO}." >&2
  exit 1
fi

install -d -m 0755 "${RUNTIME_DIR}" "${SCISCOPE_ROOT}/logs"

echo "Installing PostgreSQL 16 and pgvector through Ubuntu packages..."
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-pgvector
sudo systemctl enable --now postgresql

if [[ ! -s "${DB_ENV_FILE}" ]]; then
  umask 077
  SCISCOPE_DB_SECRET="$(openssl rand -hex 24)"
  printf 'POSTGRES_USER=sciscope\nPOSTGRES_DB=sciscope\nPOSTGRES_PASSWORD=%s\n' \
    "${SCISCOPE_DB_SECRET}" >"${DB_ENV_FILE}"
  unset SCISCOPE_DB_SECRET
fi

# shellcheck disable=SC1090
source "${DB_ENV_FILE}"

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$setup\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
    CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  ELSE
    ALTER ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  END IF;
END
\$setup\$;
SELECT 'CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER}'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB}')\gexec
SQL

umask 077
printf '127.0.0.1:5432:%s:%s:%s\n' \
  "${POSTGRES_DB}" "${POSTGRES_USER}" "${POSTGRES_PASSWORD}" >"${PGPASS_FILE}"
chmod 0600 "${DB_ENV_FILE}" "${PGPASS_FILE}"

export PGPASSFILE="${PGPASS_FILE}"
DB_DSN="postgresql://${POSTGRES_USER}@127.0.0.1:5432/${POSTGRES_DB}"

psql "${DB_DSN}" -v ON_ERROR_STOP=1 -f "${SCISCOPE_REPO}/infra/postgres/schema.sql"
psql "${DB_DSN}" -v ON_ERROR_STOP=1 -f "${SCISCOPE_REPO}/infra/postgres/stance.sql"

# Extension installation is the only database-superuser operation. Keep the
# application-owned vector table and index under the restricted project role.
sudo -u postgres psql -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'
sed '/^CREATE EXTENSION IF NOT EXISTS vector;$/d' \
  "${SCISCOPE_REPO}/infra/postgres/pgvector.sql" \
  | psql "${DB_DSN}" -v ON_ERROR_STOP=1

# IVFFlat must be trained on populated vectors. Keep bulk loading index-free;
# the guarded embed stage recreates and analyzes it after all vectors exist.
psql "${DB_DSN}" -v ON_ERROR_STOP=1 \
  -c 'DROP INDEX IF EXISTS chunk_embeddings_vector_idx;'

echo "Remote PostgreSQL/pgvector prerequisite is ready. No corpus was loaded."
echo "Next: bash scripts/check_remote_readiness.sh"
