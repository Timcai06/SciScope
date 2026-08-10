#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_ROOT="${SCISCOPE_ROOT:-/home/liu/workspaces/sciscope}"
SCISCOPE_REPO="${SCISCOPE_REPO:-${SCISCOPE_ROOT}/repo}"
RUNTIME_DIR="${SCISCOPE_ROOT}/runtime"
LOG_DIR="${SCISCOPE_ROOT}/logs"
PGPASS_FILE="${RUNTIME_DIR}/.pgpass"
PYTHON_BIN="${SCISCOPE_PYTHON:-/home/liu/miniconda3/envs/sciscope/bin/python}"
DB_DSN="${SCISCOPE_REMOTE_DB_DSN:-postgresql://sciscope@127.0.0.1:5432/sciscope}"
EMBEDDER_PATH="${SCISCOPE_EMBEDDER_PATH:-models/embedder_local/multilingual-e5-base}"

usage() {
  echo "Usage: bash scripts/run_remote_pipeline.sh <load|embed|recommend> --execute" >&2
}

stage="${1:-}"
confirmation="${2:-}"
if [[ "${confirmation}" != "--execute" ]]; then
  usage
  echo "Refusing to run without an explicit --execute confirmation." >&2
  exit 2
fi
if [[ ! "${stage}" =~ ^(load|embed|recommend)$ ]]; then
  usage
  exit 2
fi

cd "${SCISCOPE_REPO}"
install -d -m 0755 "${LOG_DIR}"
export PGPASSFILE="${PGPASS_FILE}"
export SCISCOPE_EMBEDDER_PATH="${EMBEDDER_PATH}"
export SCISCOPE_EMBED_FP16=1

case "${stage}" in
  load)
    [[ -f data/processed/papers_corpus.json ]]
    [[ -f data/processed/paper_chunks.jsonl ]]
    log_file="${LOG_DIR}/postgres-load-$(date +%Y%m%d-%H%M%S).log"
    rtk make postgres-load PYTHON="${PYTHON_BIN}" POSTGRES_DSN="${DB_DSN}" \
      2>&1 | tee "${log_file}"
    ;;
  embed)
    chunk_count="$(psql "${DB_DSN}" -Atc 'SELECT count(*) FROM paper_chunks;')"
    if [[ "${chunk_count}" == "0" ]]; then
      echo "Refusing to embed: paper_chunks is empty. Run the load stage first." >&2
      exit 1
    fi
    [[ -f "${EMBEDDER_PATH}/config.json" ]]
    log_file="${LOG_DIR}/embeddings-$(date +%Y%m%d-%H%M%S).log"
    rtk make embeddings PYTHON="${PYTHON_BIN}" POSTGRES_DSN="${DB_DSN}" \
      EMBED_BATCH_SIZE=128 EMBEDDER_PATH="${EMBEDDER_PATH}" \
      2>&1 | tee "${log_file}"
    psql "${DB_DSN}" -v ON_ERROR_STOP=1 <<'SQL'
DROP INDEX IF EXISTS chunk_embeddings_vector_idx;
CREATE INDEX chunk_embeddings_vector_idx
    ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
ANALYZE chunk_embeddings;
SQL
    ;;
  recommend)
    embedding_count="$(psql "${DB_DSN}" -Atc 'SELECT count(*) FROM chunk_embeddings;')"
    if [[ "${embedding_count}" == "0" ]]; then
      echo "Refusing to build recommendations: chunk_embeddings is empty." >&2
      exit 1
    fi
    log_file="${LOG_DIR}/recommend-model-$(date +%Y%m%d-%H%M%S).log"
    rtk make recommend-model PYTHON="${PYTHON_BIN}" POSTGRES_DSN="${DB_DSN}" \
      2>&1 | tee "${log_file}"
    ;;
esac

echo "Completed stage=${stage}; log=${log_file}"
