#!/usr/bin/env python3
"""讯飞 processed 语料 → canonical wrapper JSONL（接入分析管线的 raw 分区）。

输入：data/processed/xunfei_papers.json（摄取器产物）
输出：data/raw_canonical/iflytek/iflytek_00001.jsonl（每行一个 wrapper）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

IN = Path("data/processed/xunfei_papers.json")
OUT = Path("data/raw_canonical/iflytek/iflytek_00001.jsonl")


def to_wrapper(p: dict) -> dict:
    year = p.get("year")
    year_status = "normal"
    original_year = year
    if isinstance(year, int) and year > 2026:
        # 复用管线治理：未来年份不清除，保留原始值供审计，不计入时间窗统计
        year_status = "future_year_suspect"
        year = ""
    return {
        "source": "iflytek",
        "source_id": p.get("source_id") or "",
        "query": "xunfei delivery",
        "field_seed": p.get("field_seed") or "unknown",
        "crawled_at": p.get("crawled_at")
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "_sciscope_canonical_year": original_year or "",
        "_sciscope_year_status": year_status,
        "_sciscope_original_year": original_year,
        "_sciscope_raw_file": p.get("_sciscope_raw_file", ""),
        "raw": {
            "paper_id": p.get("paper_id") or "",
            "title": p.get("title") or "",
            "abstract": p.get("abstract") or "",
            "authors": p.get("authors") or [],
            "year": year,
            "keywords": p.get("keywords") or [],
            "full_text": p.get("full_text") or "",
        },
    }


def main() -> int:
    papers = json.loads(IN.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for p in papers:
            f.write(json.dumps(to_wrapper(p), ensure_ascii=False) + "\n")
    print(f"转换完成: {len(papers)} 条 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
