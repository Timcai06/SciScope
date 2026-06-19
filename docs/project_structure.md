# SciScope Project Structure

This repository keeps source files, data assets, and generated deliverables in
separate top-level areas.

## Top-level Rules

- `data/`: paper data and reproducible data assets.
- `output/`: generated report assets and final deliverables.
- `src/`: Python data harvesting and analysis code.
- `backend/`: FastAPI application and backend tests.
- `frontend/`: Next.js product workspace.
- `plan/`: execution plans and task breakdowns.
- `docs/`: runbooks, architecture notes, and project documentation.

## Data

- `data/sample/`: deterministic sample corpus used by local tests and demos;
  `data/sample/legacy_processed_500/` stores archived early 500-record
  normalized samples.
- `data/raw/`: harvested public-source JSONL records.
- `data/processed/`: normalized per-source paper records and the merged
  `papers_corpus_50k.json` corpus generated from analysis tables.
- `data/analysis/`: generated report-ready tables such as keyword-year matrices
  and author collaboration edges.

Raw, processed, and analysis data files are generated locally and are ignored by
Git, except for `.gitkeep` placeholders. The deterministic sample corpus is
tracked because it is needed for tests and first-run demos.

## Output

- `output/assets/sciscope_data_report/`: generated chart assets and figure
  manifest used by the data analysis report.
- `output/pdf/sciscope_data_report/`: data analysis report LaTeX source and
  final PDF.
- `output/pdf/sciscope_design/`: architecture/design LaTeX source and final PDF.

The project intentionally does not use separate `reports/` or `outputs/`
directories. Generated charts can be retained under `output/assets/`, while
final PDFs live under `output/pdf/`.
