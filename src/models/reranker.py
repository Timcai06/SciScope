"""Cross-encoder reranker (bge-reranker-v2-m3) for retrieval precision.

A bi-encoder (the e5 embedder) scores query and passage independently, which is
fast but coarse and language-biased for short cross-lingual queries. A
cross-encoder jointly encodes (query, passage) and scores their relevance
directly — far more accurate for reordering a small candidate set. We use it to
rerank the fused retrieval pool so the most topically-relevant papers surface,
especially for Chinese queries over English papers.

The model loads locally (no network) and is optional: callers fall back to the
fusion order when it is unavailable.
"""

from __future__ import annotations

import os
from functools import lru_cache

_LOCAL_PATH = os.getenv("SCISCOPE_RERANKER_PATH", "models/reranker_local/bge-reranker-v2-m3")
_MAX_LENGTH = 512


def is_available() -> bool:
    """Rerank is usable only when explicitly enabled and the model is present."""
    if os.getenv("SCISCOPE_USE_RERANKER", "1") not in ("1", "true", "True"):
        return False
    return os.path.isdir(_LOCAL_PATH)


@lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    tok = AutoTokenizer.from_pretrained(_LOCAL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(_LOCAL_PATH)
    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    if device in ("mps", "cuda"):
        model = model.half()
    model.eval()
    return tok, model, device


def score(query: str, passages: list[str], batch_size: int = 32) -> list[float]:
    """Relevance logits for (query, passage) pairs; higher = more relevant."""
    import torch

    tok, model, device = _load()
    out: list[float] = []
    for start in range(0, len(passages), batch_size):
        chunk = passages[start : start + batch_size]
        pairs = [[query, p] for p in chunk]
        inputs = tok(pairs, padding=True, truncation=True, return_tensors="pt", max_length=_MAX_LENGTH)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits.view(-1).float()
        out.extend(logits.cpu().tolist())
    return out


def rerank(query: str, items: list, text_of, top_k: int | None = None) -> list:
    """Reorder `items` by cross-encoder relevance to `query`.

    `text_of(item)` returns the passage text to score. Returns items sorted by
    descending relevance (optionally truncated to top_k). On any failure the
    original order is returned so retrieval never breaks.
    """
    if not items:
        return items
    try:
        passages = [text_of(it) for it in items]
        scores = score(query, passages)
        order = sorted(range(len(items)), key=lambda i: scores[i], reverse=True)
        ranked = [items[i] for i in order]
        return ranked[:top_k] if top_k else ranked
    except Exception:
        return items[:top_k] if top_k else items
