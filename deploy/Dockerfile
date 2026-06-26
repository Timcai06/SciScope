# SciScope backend — production image (code only).
# Models (embedder_local / reranker_local / recommend / trends) and the corpus
# are mounted as volumes at runtime, NOT baked in — see docker-compose.yml.
# The local Qwen 7B (models/llm_local) is intentionally excluded: the hosted
# deployment uses the DeepSeek API for generation.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependencies first for layer caching. On an Aliyun box, append
#   -i https://mirrors.aliyun.com/pypi/simple/
# to the pip install lines for a fast domestic mirror (see deploy/README.md).
COPY backend/requirements.txt backend/requirements.txt
# CPU-only torch FIRST, from the PyTorch CPU index. Otherwise the default
# wheel drags in ~2GB of unused CUDA/NVIDIA libraries — pure bloat on a
# CPU-only host. Pre-installing it means sentence-transformers reuses it.
RUN python -m pip install --upgrade pip \
 && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.12.1 \
 && python -m pip install -r backend/requirements.txt

# Application code (the Python brain: API + agent + services + models loaders).
# backend imports first-party packages `src` (reranker/embeddings) and
# `data_pipeline` (corpus loaders) — all three must be on the image.
COPY backend backend
COPY src src
COPY data_pipeline data_pipeline

EXPOSE 8000

# `app` is defined at module level in backend/app/main.py (app = create_app()).
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
