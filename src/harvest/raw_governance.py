from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.analysis.assets import DEFAULT_SOURCES
from src.harvest.normalize import paper_wrapper_to_paper


@dataclass
class RawGovernanceSummary:
    input_records: int
    canonical_records: int
    invalid_records: int
    canonical_dir: str
    inventory_path: str
    summary_path: str
    source_counts: dict[str, int]
    year_counts: dict[str, int]
    source_year_counts: dict[str, dict[str, int]]
    archived_files: int = 0
    deleted_archive: bool = False


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError:
                yield line_number, None


def _normalize_source(source: str) -> str:
    value = re.sub(r"[^a-z0-9_]+", "_", source.strip().lower())
    return value or "unknown"


def _record_source(wrapper: dict[str, Any], fallback: str) -> str:
    return _normalize_source(str(wrapper.get("source") or fallback or "unknown"))


def _record_year(wrapper: dict[str, Any]) -> str:
    try:
        paper = paper_wrapper_to_paper(wrapper)
    except Exception:
        return "unknown_year"
    year = paper.get("year")
    if isinstance(year, int):
        return str(year)
    match = re.search(r"(19|20)\d{2}", str(year or ""))
    return match.group(0) if match else "unknown_year"


def _record_key(wrapper: dict[str, Any]) -> str:
    try:
        paper = paper_wrapper_to_paper(wrapper)
    except Exception:
        paper = {}
    source_id = str(wrapper.get("source_id") or "").strip().lower()
    paper_id = str(paper.get("paper_id") or "").strip().lower()
    title = re.sub(r"\s+", " ", str(paper.get("title") or "")).strip().lower()
    year = str(paper.get("year") or "").strip()
    if source_id:
        return f"source_id:{source_id}"
    if paper_id:
        return f"paper_id:{paper_id}"
    return f"title_year:{title}:{year}"


def _quality_score(wrapper: dict[str, Any]) -> tuple[int, int, int, int]:
    try:
        paper = paper_wrapper_to_paper(wrapper)
    except Exception:
        return (0, 0, 0, 0)
    return (
        len(str(paper.get("full_text") or "")),
        len(str(paper.get("abstract") or "")),
        len(paper.get("keywords") or []),
        len(paper.get("authors") or []),
    )


def _inventory_role(path: Path, records: int, valid: int, canonical_new: int) -> str:
    name = path.name
    if records == 0 or valid == 0:
        return "failed_empty"
    if re.search(r"_(3|5|12|20|500)\.jsonl$", name) or name == "works_smoke.jsonl":
        return "sample"
    if canonical_new == 0:
        return "duplicate_only"
    return "contributed"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_raw_canonical(
    *,
    raw_dir: str | Path = "data/raw",
    canonical_dir: str | Path = "data/raw_canonical",
    inventory_path: str | Path = "data/raw_inventory.csv",
    summary_path: str | Path = "data/raw_canonical/summary.json",
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    archive_dir: str | Path | None = None,
    delete_archive: bool = False,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    canonical_path = Path(canonical_dir)
    inventory = Path(inventory_path)
    summary_file = Path(summary_path)

    partitions: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    partition_scores: dict[tuple[str, str], dict[str, tuple[int, int, int, int]]] = defaultdict(dict)
    inventory_rows: list[dict[str, Any]] = []
    input_records = 0
    invalid_records = 0

    source_dirs = [raw_path / source for source in sources if (raw_path / source).exists()]
    extra_dirs = [path for path in raw_path.iterdir() if path.is_dir() and path.name not in sources] if raw_path.exists() else []
    canonical_source_dirs = [
        canonical_path / source for source in sources if (canonical_path / source).exists()
    ] if canonical_path.exists() else []

    for source_dir in sorted(source_dirs + extra_dirs + canonical_source_dirs):
        source_hint = source_dir.name
        for path in sorted(source_dir.glob("*.jsonl")):
            records = 0
            valid = 0
            invalid = 0
            canonical_new = 0
            years: Counter[str] = Counter()
            sources_seen: Counter[str] = Counter()

            for _line_number, wrapper in _read_jsonl(path):
                records += 1
                input_records += 1
                if not isinstance(wrapper, dict):
                    invalid += 1
                    invalid_records += 1
                    continue
                source = _record_source(wrapper, source_hint)
                wrapper = {**wrapper, "source": source}
                year = _record_year(wrapper)
                valid += 1
                years[year] += 1
                sources_seen[source] += 1

                key = _record_key(wrapper)
                partition_key = (source, year)
                score = _quality_score(wrapper)
                existing_score = partition_scores[partition_key].get(key)
                record = {
                    **wrapper,
                    "_sciscope_raw_file": str(path),
                    "_sciscope_canonicalized_at": _utc_now(),
                    "_sciscope_canonical_year": int(year) if year.isdigit() else year,
                }
                if existing_score is None:
                    canonical_new += 1
                    partitions[partition_key][key] = record
                    partition_scores[partition_key][key] = score
                elif score > existing_score:
                    partitions[partition_key][key] = record
                    partition_scores[partition_key][key] = score

            inventory_rows.append(
                {
                    "path": str(path),
                    "source_dir": source_hint,
                    "records": records,
                    "valid_records": valid,
                    "invalid_records": invalid,
                    "canonical_new_records": canonical_new,
                    "years": ";".join(f"{year}:{count}" for year, count in sorted(years.items())),
                    "sources": ";".join(f"{source}:{count}" for source, count in sorted(sources_seen.items())),
                    "size_bytes": path.stat().st_size,
                    "role": _inventory_role(path, records, valid, canonical_new),
                }
            )

    if canonical_path.exists():
        shutil.rmtree(canonical_path)
    canonical_path.mkdir(parents=True, exist_ok=True)
    (canonical_path / ".gitkeep").write_text("", encoding="utf-8")

    source_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    source_year_counts: dict[str, Counter[str]] = defaultdict(Counter)
    canonical_records = 0

    for (source, year), records_by_key in sorted(partitions.items()):
        records = [records_by_key[key] for key in sorted(records_by_key)]
        _write_jsonl(canonical_path / source / f"{year}.jsonl", records)
        count = len(records)
        canonical_records += count
        source_counts[source] += count
        year_counts[year] += count
        source_year_counts[source][year] += count

    inventory.parent.mkdir(parents=True, exist_ok=True)
    with inventory.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "path",
            "source_dir",
            "records",
            "valid_records",
            "invalid_records",
            "canonical_new_records",
            "years",
            "sources",
            "size_bytes",
            "role",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(inventory_rows)

    archived_files = 0
    if archive_dir is not None:
        archive_path = Path(archive_dir)
        if archive_path.exists():
            shutil.rmtree(archive_path)
        for source_dir in sorted(source_dirs + extra_dirs):
            if not source_dir.exists():
                continue
            target_dir = archive_path / source_dir.name
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_dir), str(target_dir))
            archived_files += len(list(target_dir.glob("*.jsonl")))
        raw_path.mkdir(parents=True, exist_ok=True)
        (raw_path / ".gitkeep").write_text("", encoding="utf-8")
        for source in sources:
            (raw_path / source).mkdir(parents=True, exist_ok=True)
            (raw_path / source / ".gitkeep").write_text("", encoding="utf-8")
        if delete_archive and archive_path.exists():
            shutil.rmtree(archive_path)

    summary = RawGovernanceSummary(
        input_records=input_records,
        canonical_records=canonical_records,
        invalid_records=invalid_records,
        canonical_dir=str(canonical_path),
        inventory_path=str(inventory),
        summary_path=str(summary_file),
        source_counts=dict(sorted(source_counts.items())),
        year_counts={str(year): count for year, count in sorted(year_counts.items())},
        source_year_counts={
            source: {str(year): count for year, count in sorted(counter.items())}
            for source, counter in sorted(source_year_counts.items())
        },
        archived_files=archived_files,
        deleted_archive=bool(delete_archive and archive_dir is not None),
    )
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_dict = {
        "input_records": summary.input_records,
        "canonical_records": summary.canonical_records,
        "invalid_records": summary.invalid_records,
        "canonical_dir": summary.canonical_dir,
        "inventory_path": summary.inventory_path,
        "summary_path": summary.summary_path,
        "source_counts": summary.source_counts,
        "year_counts": summary.year_counts,
        "source_year_counts": summary.source_year_counts,
        "archived_files": summary.archived_files,
        "deleted_archive": summary.deleted_archive,
    }
    summary_file.write_text(json.dumps(summary_dict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary_dict
