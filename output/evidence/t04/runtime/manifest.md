# T04 remote runtime manifest

generated_utc: 2026-08-12T13:50:52Z
commit: 546eba2137a5656937718ed7dc0c790dd81fe675
host: liu-MS-7B23
kernel: Linux 7.0.0-28-generic x86_64 GNU/Linux
cpu: Intel(R) Core(TM) i7-9700 CPU @ 3.00GHz
logical_cpus: 8
memory: 31Gi total, 24Gi available
root_disk: 915G total, 543G available, 38% used
gpu: NVIDIA GeForce RTX 2080 Ti, 11264 MiB, 595.84
cuda_reported_by_driver: 13.2
python: Python 3.11.15
go: go version go1.26.5 linux/amd64
backend: http://127.0.0.1:8010

## Database counts
chunk_embeddings|367861
paper_chunks|367861
paper_embeddings|159164
papers|159164

## Vector indexes
chunk_embeddings|chunk_embeddings_pkey
chunk_embeddings|chunk_embeddings_vector_idx
paper_embeddings|paper_embeddings_pkey
paper_embeddings|paper_embeddings_vector_idx

## Readiness
{"status":"ready","checks":{"db":{"status":"configured","message":"database readiness probe succeeded"},"retrieval":{"status":"configured","message":"retrieval and pgvector readiness probe succeeded"},"model":{"status":"configured","message":"deepseek provider configured"}}}

## Scope
- Online runs use the full remote PostgreSQL corpus and complete paper/chunk embeddings.
- DeepSeek is configured in process memory; credentials are not persisted in this evidence tree.
- Offline demo is a deterministic fixture and is not model-quality evidence.
- Port 8000 belongs to another project; SciScope is isolated on port 8010.
