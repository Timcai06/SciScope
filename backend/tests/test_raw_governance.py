import json
import shutil

from src.harvest.raw_governance import build_raw_canonical


def _wrapper(source_id: str, *, year: int, abstract: str = "abstract"):
    return {
        "source": "pubmed",
        "source_id": source_id,
        "query": "large language model",
        "field_seed": "biomedicine",
        "raw": {
            "pmid": source_id,
            "title": f"Paper {source_id}",
            "abstract": abstract,
            "authors": ["Ada Chen"],
            "year": year,
            "keywords": ["rag"],
        },
    }


def test_build_raw_canonical_splits_by_source_year_and_dedupes(tmp_path):
    raw_dir = tmp_path / "raw"
    source_dir = raw_dir / "pubmed"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("pubmed_2024_5000.jsonl").write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                _wrapper("P1", year=2024, abstract="short"),
                _wrapper("P1", year=2024, abstract="longer abstract wins"),
                _wrapper("P2", year=2025),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_raw_canonical(
        raw_dir=raw_dir,
        canonical_dir=tmp_path / "raw_canonical",
        inventory_path=tmp_path / "raw_inventory.csv",
        summary_path=tmp_path / "raw_canonical" / "summary.json",
    )

    assert summary["input_records"] == 3
    assert summary["canonical_records"] == 2
    assert summary["source_counts"] == {"pubmed": 2}
    assert summary["year_counts"] == {"2024": 1, "2025": 1}

    y2024 = tmp_path / "raw_canonical" / "pubmed" / "2024.jsonl"
    y2025 = tmp_path / "raw_canonical" / "pubmed" / "2025.jsonl"
    assert y2024.exists()
    assert y2025.exists()
    record = json.loads(y2024.read_text(encoding="utf-8").strip())
    assert record["raw"]["abstract"] == "longer abstract wins"
    assert record["_sciscope_canonical_year"] == 2024
    assert record["_sciscope_raw_file"].endswith("pubmed_2024_5000.jsonl")

    inventory = (tmp_path / "raw_inventory.csv").read_text(encoding="utf-8")
    assert "canonical_new_records" in inventory
    assert "pubmed_2024_5000.jsonl" in inventory


def test_build_raw_canonical_preserves_existing_canonical_when_raw_is_empty(tmp_path):
    raw_dir = tmp_path / "raw"
    source_dir = raw_dir / "pubmed"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("pubmed_2024_5000.jsonl").write_text(
        json.dumps(_wrapper("P1", year=2024), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    canonical_dir = tmp_path / "raw_canonical"
    build_raw_canonical(
        raw_dir=raw_dir,
        canonical_dir=canonical_dir,
        inventory_path=tmp_path / "raw_inventory.csv",
        summary_path=canonical_dir / "summary.json",
    )

    shutil.rmtree(raw_dir)
    raw_dir.mkdir()
    summary = build_raw_canonical(
        raw_dir=raw_dir,
        canonical_dir=canonical_dir,
        inventory_path=tmp_path / "raw_inventory.csv",
        summary_path=canonical_dir / "summary.json",
    )

    assert summary["canonical_records"] == 1
    assert (canonical_dir / "pubmed" / "2024.jsonl").exists()


def test_build_raw_canonical_routes_future_years_to_suspect_partition(tmp_path):
    raw_dir = tmp_path / "raw"
    source_dir = raw_dir / "pubmed"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("pubmed_future.jsonl").write_text(
        json.dumps(_wrapper("P1", year=2027), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    canonical_dir = tmp_path / "raw_canonical"
    summary = build_raw_canonical(
        raw_dir=raw_dir,
        canonical_dir=canonical_dir,
        inventory_path=tmp_path / "raw_inventory.csv",
        summary_path=canonical_dir / "summary.json",
        max_year=2026,
    )

    assert summary["canonical_records"] == 1
    assert summary["source_year_counts"]["pubmed"] == {"future_year_suspect": 1}
    assert not (canonical_dir / "pubmed" / "2027.jsonl").exists()
    suspect_path = canonical_dir / "pubmed" / "future_year_suspect.jsonl"
    record = json.loads(suspect_path.read_text(encoding="utf-8").strip())
    assert record["_sciscope_original_year"] == 2027
    assert record["_sciscope_year_status"] == "future_year_suspect"
