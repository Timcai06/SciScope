"""Backfill missing abstracts for canonical records via OpenAlex (by DOI).

Many crossref records arrive without an abstract. This queries OpenAlex by DOI,
reconstructs the abstract from its inverted index, and writes it back into the
canonical record's ``raw.abstract`` so the existing normalizer picks it up on
the next rebuild. Bounded by --limit, rate-limited, resumable (skips records
that already have an abstract or were already attempted).

Usage:
    python -m src.harvest.abstract_backfill --source crossref \
        --canonical-dir data/raw_canonical --limit 500 --mailto you@example.com
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.harvest.normalize import _restore_openalex_abstract

OPENALEX = "https://api.openalex.org/works/doi:"


def _iter_files(canonical_dir: Path, source: str) -> list[Path]:
    # canonical 分区按 source/year 保存为 jsonl，按路径顺序扫描便于 checkpoint 对账。
    return sorted((canonical_dir / source).glob("*.jsonl"))


def _existing_abstract(record: dict[str, Any]) -> str:
    raw = record.get("raw") or {}
    return str(raw.get("abstract") or "").strip()


def _doi(record: dict[str, Any]) -> str:
    sid = str(record.get("source_id") or (record.get("raw") or {}).get("DOI") or "").strip()
    return sid.lower() if sid.lower().startswith("10.") else ""


def _fetch_openalex(doi: str, mailto: str, timeout: int) -> dict[str, Any] | None:
    # OpenAlex by DOI 仅做补摘要补齐；对单条记录失败吞掉，避免把整批任务打断。
    url = OPENALEX + urllib.parse.quote(doi)
    if mailto:
        url += "?mailto=" + urllib.parse.quote(mailto)
    req = urllib.request.Request(url, headers={"User-Agent": f"SciScope/1.0 ({mailto or 'research'})"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def backfill(
    *,
    source: str = "crossref",
    canonical_dir: Path = Path("data/raw_canonical"),
    limit: int = 500,
    mailto: str = "",
    sleep_seconds: float = 0.2,
    timeout: int = 25,
    workers: int = 5,
) -> dict[str, int]:
    # 这个流程的核心是“可恢复 + 不重复尝试”：
    # - 只处理无 abstract 且未标记过 attempt 的记录；
    # - 批次请求后立即 checkpoint 落盘；
    # - _sciscope_abstract_attempt/soure 记录避免重复回写。
    import socket
    from concurrent.futures import ThreadPoolExecutor

    # Hard cap so a stalled connection can't hang the whole crawl indefinitely.
    socket.setdefaulttimeout(timeout)

    stats = {"scanned": 0, "needed": 0, "filled": 0, "missed": 0}
    remaining = limit

    def _flush(path: Path, records: list) -> None:
        # 每个批次完成后做 `.jsonl.tmp` 原子替换，发生中断可直接从上一次落盘恢复。
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _apply(record: dict, data: dict | None) -> None:
        record["_sciscope_abstract_attempt"] = True
        abstract = _restore_openalex_abstract((data or {}).get("abstract_inverted_index")) if data else ""
        if abstract:
            record.setdefault("raw", {})["abstract"] = abstract
            record["_sciscope_abstract_source"] = "openalex_doi"
            stats["filled"] += 1
        else:
            stats["missed"] += 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for path in _iter_files(canonical_dir, source):
            if remaining <= 0:
                break
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            pending = [r for r in records if not _existing_abstract(r) and not r.get("_sciscope_abstract_attempt") and _doi(r)]
            stats["scanned"] += len(records)
            if not pending:
                continue
            if remaining < len(pending):
                pending = pending[:remaining]
            # 批次处理 + 并发请求：按 workers 并发，既控制吞吐也便于低收益尾部及时观察。
            batch = max(workers * 8, 40)
            for start in range(0, len(pending), batch):
                group = pending[start : start + batch]
                stats["needed"] += len(group)
                remaining -= len(group)
                results = list(pool.map(lambda r: _fetch_openalex(_doi(r), mailto, timeout), group))
                for record, data in zip(group, results):
                    _apply(record, data)
                _flush(path, records)
                print(f"  checkpoint {path.name}: filled={stats['filled']} missed={stats['missed']}", flush=True)
                if sleep_seconds:
                    time.sleep(sleep_seconds)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing abstracts via OpenAlex DOI lookup")
    parser.add_argument("--source", default="crossref")
    parser.add_argument("--canonical-dir", type=Path, default=Path("data/raw_canonical"))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--mailto", default="")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    stats = backfill(
        source=args.source, canonical_dir=args.canonical_dir, limit=args.limit,
        mailto=args.mailto, sleep_seconds=args.sleep_seconds, timeout=args.timeout,
        workers=args.workers,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
