# Next Sprint Plan

## Sprint Goal

Move from foundation slice to real-data SciScope. The sprint is complete when a 500-paper public corpus can be harvested, normalized, analyzed, and served through existing APIs.

## Task 1: Create Data Directories

Create:

```text
data/raw/
data/processed/
indices/
models/
graphs/
reports/assets/
src/harvest/
src/analysis/
```

Acceptance:

- Directories exist.
- `.gitkeep` files added where needed.

## Task 2: OpenAlex Pilot Harvester

Implement:

```text
src/harvest/openalex_client.py
src/harvest/cli.py
```

Target command:

```bash
make harvest-sample SOURCE=openalex LIMIT=500
```

Acceptance:

- Generates `data/raw/openalex/works_sample.jsonl`.
- Stores source id, title, abstract, authors, year, concepts/topics, DOI, URL, field candidate.

## Task 3: Normalization Pipeline

Implement:

```text
src/harvest/normalize.py
```

Target command:

```bash
make normalize
```

Acceptance:

- Generates `data/processed/papers.parquet`.
- Generates `data/processed/data_quality.json`.
- Handles missing abstract, missing keywords, and duplicate records.

## Task 4: First Real Analysis Assets

Implement:

```text
src/analysis/distribution.py
src/analysis/keywords.py
src/analysis/collaboration.py
```

Target command:

```bash
make analyze
```

Acceptance:

- Generates publication trend.
- Generates field distribution.
- Generates keyword counts.
- Generates author collaboration graph.

## Task 5: Backend Switch to Processed Data

Update corpus service so backend can read:

- sample JSON for tests.
- processed Parquet for real mode.

Acceptance:

- Existing tests still pass.
- `/api/dashboard/overview` works on harvested 500-paper corpus.

## Task 6: Frontend Real Data Smoke

Acceptance:

- Overview displays real 500-paper corpus metrics.
- Evidence chat returns papers from harvested corpus.

## Task 7: Sprint Verification

Run:

```bash
make test
make harvest-sample LIMIT=500
make normalize
make analyze
make dev
make smoke
```

Sprint is accepted when these commands pass or documented external API limitations are clearly isolated.
