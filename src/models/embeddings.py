"""Embedding model wrapper for SciScope retrieval.

Uses a local sentence-transformers model so the embedding step is reproducible
and offline. The model is part of the deliverable "model files" and is cached
under ``models/embedder/``.

The default model ``intfloat/multilingual-e5-base`` produces 768-dim vectors
(matching ``chunk_embeddings.embedding vector(768)`` in ``pgvector.sql``) and
handles Chinese questions over an English corpus. e5 models require an
instruction prefix: ``query:`` for search queries and ``passage:`` for indexed
documents.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

DEFAULT_MODEL = os.getenv("SCISCOPE_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
EMBEDDING_DIM = 768
_CACHE_DIR = Path(os.getenv("SCISCOPE_EMBEDDER_DIR", "models/embedder"))
# Optional local model directory (e.g. an offline/mirror download). When set,
# the model is loaded from this path but the stored ``model_name`` tag stays
# canonical so DB embedding_model tags remain consistent across machines.
_LOCAL_PATH = os.getenv("SCISCOPE_EMBEDDER_PATH", "")


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class SciScopeEmbedder:
    """Thin wrapper around a sentence-transformers model with e5 prefixes."""

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: Path | None = None) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        cache = str(cache_dir or _CACHE_DIR)
        Path(cache).mkdir(parents=True, exist_ok=True)
        load_target = _LOCAL_PATH if _LOCAL_PATH and Path(_LOCAL_PATH).exists() else model_name
        self.model = SentenceTransformer(load_target, cache_folder=cache)
        dim = self.model.get_sentence_embedding_dimension()
        if dim != EMBEDDING_DIM:
            raise ValueError(
                f"Model {model_name} has dim {dim}, expected {EMBEDDING_DIM} to match pgvector schema"
            )
        # Half precision roughly doubles MPS throughput; output is cast back to
        # float32 for pgvector. Disable with SCISCOPE_EMBED_FP16=0 if NaNs appear.
        self.fp16 = _parse_bool(os.getenv("SCISCOPE_EMBED_FP16"), default=True)
        if self.fp16 and str(self.model.device).startswith(("mps", "cuda")):
            self.model = self.model.half()

    def encode_passages(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        prefixed = [f"passage: {text}" for text in texts]
        return self._encode(prefixed, batch_size)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([f"query: {text}"], batch_size=1)[0]

    def _encode(self, texts: list[str], batch_size: int) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)


@lru_cache(maxsize=1)
def get_embedder(model_name: str = DEFAULT_MODEL) -> SciScopeEmbedder:
    return SciScopeEmbedder(model_name)
