#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_ROOT="${SCISCOPE_ROOT:-/home/liu/workspaces/sciscope}"
SCISCOPE_REPO="${SCISCOPE_REPO:-${SCISCOPE_ROOT}/repo}"
RUNTIME_DIR="${SCISCOPE_ROOT}/runtime"
PGPASS_FILE="${RUNTIME_DIR}/.pgpass"
PYTHON_BIN="${SCISCOPE_PYTHON:-/home/liu/miniconda3/envs/sciscope/bin/python}"
DB_DSN="${SCISCOPE_REMOTE_DB_DSN:-postgresql://sciscope@127.0.0.1:5432/sciscope}"
XUNFEI_ARCHIVE="${SCISCOPE_ROOT}/data/incoming/xunfei/environment.tar.gz"

failures=0

check_path() {
  local label="$1"
  local target="$2"
  if [[ -e "${target}" ]]; then
    printf 'PASS  %-24s %s\n' "${label}" "${target}"
  else
    printf 'FAIL  %-24s %s\n' "${label}" "${target}"
    failures=$((failures + 1))
  fi
}

echo "=== CODE AND HARDWARE ==="
check_path repository "${SCISCOPE_REPO}/.git"
check_path python "${PYTHON_BIN}"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
  echo "FAIL  nvidia-smi"
  failures=$((failures + 1))
fi

if [[ -x "${PYTHON_BIN}" ]]; then
  "${PYTHON_BIN}" -c \
    'import torch; assert torch.cuda.is_available(); print(f"PASS  torch_cuda              {torch.__version__} / {torch.cuda.get_device_name(0)}")' \
    || failures=$((failures + 1))
fi

echo
echo "=== EMBEDDING INPUTS ==="
check_path papers_corpus "${SCISCOPE_REPO}/data/processed/papers_corpus.json"
check_path paper_chunks "${SCISCOPE_REPO}/data/processed/paper_chunks.jsonl"
check_path embedder "${SCISCOPE_REPO}/models/embedder_local/multilingual-e5-base/config.json"
check_path reranker "${SCISCOPE_REPO}/models/reranker_local/bge-reranker-v2-m3/config.json"

echo
echo "=== DATABASE ==="
if [[ -r "${PGPASS_FILE}" ]] && command -v psql >/dev/null 2>&1; then
  export PGPASSFILE="${PGPASS_FILE}"
  if vector_version="$(psql "${DB_DSN}" -Atc \
    'SELECT extversion FROM pg_extension WHERE extname = '\''vector'\'';' 2>/dev/null)"; then
    printf 'PASS  pgvector                 %s\n' "${vector_version}"
    psql "${DB_DSN}" -Atc \
      "SELECT 'papers='||count(*) FROM papers UNION ALL SELECT 'chunks='||count(*) FROM paper_chunks UNION ALL SELECT 'chunk_embeddings='||count(*) FROM chunk_embeddings;"
  else
    echo "FAIL  PostgreSQL/pgvector is not ready"
    failures=$((failures + 1))
  fi
else
  echo "FAIL  PostgreSQL credentials or psql missing"
  failures=$((failures + 1))
fi

echo
echo "=== XUNFEI DELIVERY ==="
if [[ -f "${XUNFEI_ARCHIVE}" ]]; then
  du -h "${XUNFEI_ARCHIVE}"
  if [[ -e "${XUNFEI_ARCHIVE}.aria2" ]]; then
    echo "WAIT  Xunfei archive is still downloading"
  else
    echo "PASS  Xunfei archive download completed; integrity/admission not yet approved"
  fi
else
  echo "WAIT  Xunfei archive is not present"
fi

echo
if (( failures > 0 )); then
  echo "NOT READY: ${failures} prerequisite check(s) failed."
  exit 1
fi
echo "READY: compute prerequisites passed. No embedding or evaluation was run."
