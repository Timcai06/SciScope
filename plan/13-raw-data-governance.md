# SciScope Raw Data Governance

## Objective

Raw paper records are governed by the two dimensions that matter most to the competition task:

- source: where the record came from, such as OpenAlex, arXiv, PubMed, PMC, Crossref, or DOAJ
- year: the publication year extracted from the source record through the normal SciScope parser

The raw layer keeps records source-separated and year-partitioned. Cross-source fusion remains a processed-layer responsibility.

## Canonical Layout

```text
data/raw_canonical/
  arxiv/
    2022.jsonl
    2023.jsonl
  pubmed/
    2024.jsonl
  doaj/
    unknown_year.jsonl
  summary.json

data/raw_inventory.csv
```

`data/raw` is now a landing zone for new harvest batches. It should not be used directly for analysis once canonical raw exists.

## Rules

- Merge all historical raw batches into `data/raw_canonical/<source>/<year>.jsonl`.
- Deduplicate inside each `source + year` partition.
- Preserve early harvested records if they contribute unique source records.
- Preserve records with missing year under `unknown_year.jsonl`.
- Do not perform cross-source deduplication at the raw layer.
- Keep source, source_id, raw payload, and `_sciscope_raw_file` provenance on each canonical record.
- Delete temporary `raw_archive` after canonical verification to save local disk.

## Commands

```bash
make raw-canonical
```

Builds or refreshes canonical raw partitions. If historical raw files have already been removed, this command preserves existing canonical partitions and can merge newly harvested files from `data/raw`.

```bash
make raw-governance
```

Builds canonical raw partitions, archives old source directories, then deletes the archive copy after canonical verification.

## Current Baseline

After the June 20 raw governance pass:

- raw input records absorbed: 220,278
- canonical raw records: 169,324
- canonical source/year files: 147
- source counts:
  - openalex: 41,477
  - arxiv: 29,760
  - pmc: 30,104
  - crossref: 28,500
  - pubmed: 28,163
  - doaj: 11,320
- recent year counts:
  - 2022: 31,038
  - 2023: 30,418
  - 2024: 30,881
  - 2025: 33,232
  - 2026: 34,690

Temporary archive files were removed after canonical verification.

## Downstream Contract

Analysis and processed corpus commands should read from `data/raw_canonical`, not directly from `data/raw`.

`data/raw` is reserved for future incremental harvest batches. Running `make raw-canonical` after new harvests merges those batches into the canonical source/year layout.
