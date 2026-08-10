#!/usr/bin/env python3
"""Audit the Xunfei delivery ZIP without extracting or admitting its contents."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "xunfei-delivery-audit/v1"
METADATA_MARKERS = (
    "license",
    "readme",
    "manifest",
    "metadata",
    "schema",
    "usage",
    "授权",
    "许可",
    "说明",
)
SOURCE_PATTERNS = {
    "arxiv": re.compile(r"^arxiv_(?P<id>\d{4}\.\d{4,5})(?:v\d+)?\.pdf$", re.I),
    "openalex": re.compile(r"^openalex_(?P<id>W\d+)\.pdf$", re.I),
    "biorxiv": re.compile(
        r"^biorxiv_(?P<doi_prefix>\d+\.\d+)_(?P<id>[\d.]+)\.pdf$", re.I
    ),
    "medrxiv": re.compile(
        r"^medrxiv_(?P<doi_prefix>\d+\.\d+)_(?P<id>[\d.]+)\.pdf$", re.I
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _external_id(name: str) -> tuple[str, str] | None:
    for source, pattern in SOURCE_PATTERNS.items():
        match = pattern.fullmatch(name)
        if not match:
            continue
        value = match.group("id")
        if source in {"biorxiv", "medrxiv"}:
            value = f"{match.group('doi_prefix')}/{value}"
        return source, value
    return None


def _normalize_external_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "doi:",
        "https://openalex.org/",
        "http://openalex.org/",
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    if re.fullmatch(r"\d{4}\.\d{4,5}v\d+", text):
        text = re.sub(r"v\d+$", "", text)
    return text


def _corpus_overlap(corpus_path: Path, parsed_ids: list[dict[str, str]]) -> dict[str, Any]:
    with corpus_path.open("r", encoding="utf-8") as handle:
        corpus = json.load(handle)
    identifiers: set[str] = set()
    for record in corpus:
        for key in ("paper_id", "source_id", "doi"):
            normalized = _normalize_external_id(record.get(key))
            if normalized:
                identifiers.add(normalized)
    matches = [
        item
        for item in parsed_ids
        if _normalize_external_id(item["external_id"]) in identifiers
    ]
    by_source = collections.Counter(item["source"] for item in matches)
    return {
        "corpus_path": str(corpus_path.resolve()),
        "corpus_record_count": len(corpus),
        "incoming_identifier_matches": len(matches),
        "incoming_identifier_match_by_source": dict(sorted(by_source.items())),
        "match_examples": matches[:20],
        "interpretation": "identifier_overlap_candidate_not_content_deduplication",
    }


def audit_zip(
    path: Path, *, verify_crc: bool = True, corpus_path: Path | None = None
) -> dict[str, Any]:
    path = path.resolve()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        files = [item for item in infos if not item.is_dir()]
        names = [item.filename for item in files]
        basenames = [PurePosixPath(name).name for name in names]

        suspicious_paths = [
            name
            for name in names
            if name.startswith("/") or ".." in PurePosixPath(name).parts
        ]
        duplicate_names = sorted(
            name for name, count in collections.Counter(names).items() if count > 1
        )
        by_crc_size: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
        for item in files:
            if item.file_size:
                by_crc_size[(item.CRC, item.file_size)].append(item.filename)
        duplicate_content_candidates = [
            group for group in by_crc_size.values() if len(group) > 1
        ]

        source_counts: collections.Counter[str] = collections.Counter()
        parsed_ids: list[dict[str, str]] = []
        invalid_names: list[str] = []
        for basename in basenames:
            parsed = _external_id(basename)
            if parsed is None:
                invalid_names.append(basename)
                continue
            source, external_id = parsed
            source_counts[source] += 1
            parsed_ids.append(
                {"filename": basename, "source": source, "external_id": external_id}
            )

        metadata_candidates = [
            name for name in names if any(marker in name.lower() for marker in METADATA_MARKERS)
        ]
        crc_failure = archive.testzip() if verify_crc else None

    top_levels = collections.Counter(
        PurePosixPath(item.filename).parts[0]
        for item in infos
        if PurePosixPath(item.filename).parts
    )
    extension_counts = collections.Counter(
        PurePosixPath(name).suffix.lower() or "<none>" for name in names
    )
    zero_byte_files = [item.filename for item in files if item.file_size == 0]
    encrypted_files = [item.filename for item in files if item.flag_bits & 0x1]

    blocking_reasons: list[str] = []
    if crc_failure:
        blocking_reasons.append(f"zip_crc_failure:{crc_failure}")
    if suspicious_paths:
        blocking_reasons.append("unsafe_archive_paths")
    if duplicate_names:
        blocking_reasons.append("duplicate_archive_names")
    if zero_byte_files:
        blocking_reasons.append("zero_byte_files")
    if invalid_names:
        blocking_reasons.append("unparseable_stable_ids")
    # A filename that looks like LICENSE/README is only a discovery hint.  This
    # inventory audit never interprets legal terms or upgrades a batch to
    # admitted; that requires a separately reviewed D01 admission manifest.
    if not metadata_candidates:
        blocking_reasons.append("metadata_files_missing")
    blocking_reasons.extend(
        ["license_unverified", "usage_rights_unverified", "field_mapping_unverified"]
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "artifact": {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "crc_verified": verify_crc,
            "crc_failure": crc_failure,
        },
        "inventory": {
            "entry_count": len(infos),
            "file_count": len(files),
            "uncompressed_bytes": sum(item.file_size for item in files),
            "compressed_bytes": sum(item.compress_size for item in files),
            "top_levels": dict(sorted(top_levels.items())),
            "extensions": dict(sorted(extension_counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "parsed_stable_id_count": len(parsed_ids),
            "invalid_name_count": len(invalid_names),
            "invalid_name_examples": invalid_names[:20],
            "zero_byte_files": zero_byte_files,
            "encrypted_file_count": len(encrypted_files),
            "suspicious_paths": suspicious_paths,
            "duplicate_names": duplicate_names,
            "duplicate_content_candidate_count": len(duplicate_content_candidates),
            "metadata_candidates": metadata_candidates,
        },
        "admission": {
            "status": "blocked_pending_d01_manifest_review",
            "blocking_reasons": blocking_reasons,
            "allowed_action": "retain_in_controlled_incoming_only",
            "forbidden_actions": [
                "canonical_import",
                "database_import",
                "embedding",
                "public_export",
            ]
        },
    }
    if corpus_path is not None:
        report["existing_corpus_overlap"] = _corpus_overlap(corpus_path, parsed_ids)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Optional existing papers_corpus.json for identifier-overlap analysis.",
    )
    parser.add_argument(
        "--skip-crc",
        action="store_true",
        help="Skip the full payload read; the report will record crc_verified=false.",
    )
    args = parser.parse_args()
    report = audit_zip(
        args.archive, verify_crc=not args.skip_crc, corpus_path=args.corpus
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
