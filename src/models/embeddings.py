"""Embedding model wrapper for SciScope retrieval.

维护级口径（不可变）：
* 仅承载向量化行为，不混入检索策略或业务打分规则。
* 使用本地 `sentence-transformers`，模型与本地缓存目录可复现；
  `SCISCOPE_EMBEDDER_DIR` 和 `SCISCOPE_EMBEDDER_PATH` 仅影响加载来源，
  但写库/写文件时继续沿用 `model_name` 标签。
* 默认模型 `intfloat/multilingual-e5-base` 约定产出 768 维向量，并要求
  在查询/文档侧分别加 `query:` / `passage:` 前缀，保障检索语义口径一致。
* `normalize_embeddings=True` + `astype(np.float32)` 是本系统统一向量规范；
  任何后续消费者（尤其是 pgvector 相似度计算）都假定该规范成立。
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
        # model_name 既是模型加载入口，也是 chunk/paper 向量元数据中的“口径标签”。
        # 若切换模型，必须以模型名变化触发重建索引/向量，否则会发生口径污染。
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
        """Encode retrieval chunks (title/abstract/keywords/full_text fragments).

        Invariant: 同一次运行里一批 `texts` 的尺寸顺序与返回向量顺序一一对应；
        下游 upsert 以此建立 `chunk_uid -> embedding` 的稳定映射。
        """
        prefixed = [f"passage: {text}" for text in texts]
        return self._encode(prefixed, batch_size)

    def encode_query(self, text: str) -> np.ndarray:
        """Encode single query text with the query-prefix contract."""
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
