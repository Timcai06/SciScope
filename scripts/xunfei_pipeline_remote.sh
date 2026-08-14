#!/bin/bash
# 讯飞数据全链路入库（在 2080 上执行，幂等可重跑）
# 用法: bash scripts/xunfei_pipeline_remote.sh
set -euo pipefail
cd ~/sciscope

PY=~/miniconda3/envs/sciscope/bin/python
export PGPASSFILE=/home/liu/workspaces/sciscope/runtime/.pgpass
DSN="postgresql://sciscope@127.0.0.1:5432/sciscope"

echo "=== [1/5] 解包 ==="
if [ ! -d data/raw/iflytek/environment ]; then
  tar -xzf data/raw/iflytek/environment.tar.gz -C data/raw/iflytek
fi
PDF_COUNT=$(ls data/raw/iflytek/environment/*.pdf | wc -l)
echo "PDF 数: $PDF_COUNT"

echo "=== [2/5] 摄取 PDF → processed ==="
$PY scripts/ingest_xunfei_pdfs.py \
  --pdf-dir data/raw/iflytek/environment \
  --out data/processed/xunfei_papers.json \
  --log data/processed/xunfei_ingest.log || {
  echo "摄取有失败项，查看日志 data/processed/xunfei_ingest.log"
}

echo "=== [3/5] 生成 chunks ==="
$PY -m src.infra.cli chunks \
  --input data/processed/xunfei_papers.json \
  --output data/processed/xunfei_chunks.jsonl \
  --summary data/processed/xunfei_chunks.summary.json

echo "=== [4/5] 入库（upsert）==="
$PY -m src.infra.cli load-postgres \
  --dsn "$DSN" \
  --papers data/processed/xunfei_papers.json \
  --chunks data/processed/xunfei_chunks.jsonl

echo "=== [5/5] 向量化（增量 resume，GPU）==="
HF_ENDPOINT=https://hf-mirror.com $PY -m src.models.build_embeddings \
  --dsn "$DSN" \
  --chunks data/processed/xunfei_chunks.jsonl \
  --batch-size 256

echo "=== 完成 ==="
psql "$DSN" -t -c "SELECT source, count(*) FROM papers WHERE source='iflytek' GROUP BY 1;"
psql "$DSN" -t -c "SELECT count(*) FROM chunk_embeddings;"
