from __future__ import annotations

import zipfile
import json

from scripts.audit_xunfei_delivery import audit_zip


def _zip(tmp_path, members):
    path = tmp_path / "delivery.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members:
            archive.writestr(name, content)
    return path


def test_unknown_license_and_zero_byte_file_block_admission(tmp_path):
    path = _zip(
        tmp_path,
        [
            ("environment/arxiv_2404.11939.pdf", b"pdf"),
            ("environment/biorxiv_10.1101_2025.10.13.682097.pdf", b""),
        ],
    )

    report = audit_zip(path)

    assert report["admission"]["status"] == "blocked_pending_d01_manifest_review"
    assert "license_unverified" in report["admission"]["blocking_reasons"]
    assert "metadata_files_missing" in report["admission"]["blocking_reasons"]
    assert "zero_byte_files" in report["admission"]["blocking_reasons"]
    assert report["inventory"]["source_counts"] == {"arxiv": 1, "biorxiv": 1}


def test_metadata_does_not_override_unsafe_path(tmp_path):
    path = _zip(
        tmp_path,
        [
            ("environment/LICENSE.txt", b"unknown"),
            ("../openalex_W123.pdf", b"pdf"),
        ],
    )

    report = audit_zip(path)

    assert report["admission"]["status"] == "blocked_pending_d01_manifest_review"
    assert "unsafe_archive_paths" in report["admission"]["blocking_reasons"]
    assert "license_unverified" in report["admission"]["blocking_reasons"]
    assert report["inventory"]["metadata_candidates"] == ["environment/LICENSE.txt"]


def test_parseable_sources_are_counted(tmp_path):
    path = _zip(
        tmp_path,
        [
            ("environment/arxiv_2404.11939.pdf", b"a"),
            ("environment/openalex_W1989668498.pdf", b"b"),
            ("environment/biorxiv_10.1101_2020.08.18.255307.pdf", b"c"),
            ("environment/medrxiv_10.1101_19003194.pdf", b"d"),
            ("environment/biorxiv_10.64898_2025.12.02.691896.pdf", b"e"),
        ],
    )

    report = audit_zip(path, verify_crc=False)

    assert report["inventory"]["parsed_stable_id_count"] == 5
    assert report["inventory"]["invalid_name_count"] == 0
    assert report["artifact"]["crc_verified"] is False


def test_existing_corpus_overlap_is_identifier_only(tmp_path):
    path = _zip(tmp_path, [("environment/arxiv_2404.11939.pdf", b"a")])
    corpus = tmp_path / "papers.json"
    corpus.write_text(
        json.dumps(
            [
                {
                    "paper_id": "other",
                    "source_id": "http://arxiv.org/abs/2404.11939v2",
                    "doi": "",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = audit_zip(path, verify_crc=False, corpus_path=corpus)

    overlap = report["existing_corpus_overlap"]
    assert overlap["incoming_identifier_matches"] == 1
    assert overlap["incoming_identifier_match_by_source"] == {"arxiv": 1}
    assert overlap["interpretation"] == "identifier_overlap_candidate_not_content_deduplication"
