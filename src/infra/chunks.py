from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MAX_CHARS = 1800
DEFAULT_OVERLAP_CHARS = 180


def normalize_identifier(value: str) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return normalized


def stable_uid(*parts: Any) -> str:
    payload = "\u241f".join(normalize_identifier(str(part)) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def paper_uid(paper: dict[str, Any]) -> str:
    source = str(paper.get("source") or "unknown")
    source_id = str(paper.get("source_id") or paper.get("paper_id") or "").strip()
    if source_id:
        return stable_uid("paper", source, source_id)
    return stable_uid("paper", paper.get("title", ""), paper.get("year", ""))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    latin_tokens = len(re.findall(r"[A-Za-z0-9]+", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return max(1, latin_tokens + cjk_chars)


def split_text(text: str, *, max_chars: int = DEFAULT_MAX_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        if end < len(cleaned):
            sentence_end = max(cleaned.rfind(".", start, end), cleaned.rfind("。", start, end))
            if sentence_end > start + max_chars // 2:
                end = sentence_end + 1
        chunks.append(cleaned[start:end].strip())
        if end >= len(cleaned):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]


def build_paper_chunks(
    paper: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    uid = paper_uid(paper)
    chunks: list[dict[str, Any]] = []
    candidates = [
        ("title_abstract", "abstract", "\n".join(part for part in [paper.get("title"), paper.get("abstract")] if part)),
        ("full_text", "full_text", paper.get("full_text") or ""),
        ("keywords", "keywords", ", ".join(str(keyword) for keyword in paper.get("keywords") or [] if keyword)),
    ]

    chunk_index = 0
    for chunk_type, source_field, text in candidates:
        for chunk_text in split_text(str(text or ""), max_chars=max_chars, overlap_chars=overlap_chars):
            chunks.append(
                {
                    "chunk_uid": stable_uid("chunk", uid, chunk_index, chunk_type, chunk_text),
                    "paper_uid": uid,
                    "paper_id": str(paper.get("paper_id") or ""),
                    "source": str(paper.get("source") or ""),
                    "source_id": str(paper.get("source_id") or ""),
                    "title": str(paper.get("title") or ""),
                    "year": paper.get("year"),
                    "field": str(paper.get("field") or "unknown"),
                    "chunk_index": chunk_index,
                    "chunk_type": chunk_type,
                    "source_field": source_field,
                    "text": chunk_text,
                    "token_estimate": estimate_tokens(chunk_text),
                    "metadata": {
                        "query": paper.get("query") or "",
                        "field_seed": paper.get("field_seed") or "",
                        "is_recent_window": bool(paper.get("is_recent_window")),
                    },
                }
            )
            chunk_index += 1
    return chunks


def build_chunk_assets(
    *,
    input_path: str | Path = "data/processed/papers_corpus.json",
    output_path: str | Path = "data/processed/paper_chunks.jsonl",
    summary_path: str | Path = "data/processed/paper_chunks.summary.json",
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> dict[str, Any]:
    source = Path(input_path)
    output = Path(output_path)
    summary = Path(summary_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)

    papers = json.loads(source.read_text(encoding="utf-8")) if source.exists() else []
    total_chunks = 0
    chunks_by_type: dict[str, int] = {}
    chunks_with_full_text = 0
    token_estimate = 0

    with output.open("w", encoding="utf-8") as handle:
        for paper in papers:
            chunks = build_paper_chunks(paper, max_chars=max_chars, overlap_chars=overlap_chars)
            for chunk in chunks:
                handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total_chunks += 1
                chunks_by_type[chunk["chunk_type"]] = chunks_by_type.get(chunk["chunk_type"], 0) + 1
                token_estimate += int(chunk["token_estimate"])
                if chunk["chunk_type"] == "full_text":
                    chunks_with_full_text += 1

    result = {
        "input_papers": len(papers),
        "chunks": total_chunks,
        "chunks_by_type": dict(sorted(chunks_by_type.items())),
        "full_text_chunks": chunks_with_full_text,
        "token_estimate": token_estimate,
        "output": str(output),
    }
    summary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
