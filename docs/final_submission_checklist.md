# SciScope Final Submission Checklist

This checklist is the handoff surface for the final report-polish pass. It keeps
the work focused on presentation, consistency, and judging clarity.

## Scope Lock

- [x] Do not add data sources, agent tools, frontend scope, release packaging, or
  broad refactors.
- [x] Treat the lower layers as frozen: data, RAG, agent, model assets, and
  architecture are already saturated for this submission.
- [x] Spend the final effort on narrative amplification, format polish, and
  numeric consistency.

## Numeric Truth Sources

- [x] Data analysis report uses `data/analysis/summary.json` and
  `output/assets/sciscope_data_report/data_layer_readiness.json`.
- [x] Processed corpus file uses `data/processed/papers_corpus.summary.json`.
- [x] RAG chunk file uses `data/processed/paper_chunks.summary.json`.
- [x] Runtime service/index counts use PostgreSQL table counts.
- [x] Evaluation metrics use `output/eval/eval_report.json`.

## Current Canonical Metrics

- Raw records: 169,324.
- Analysis records: 168,447.
- Main 2022-2026 analysis-window records: 159,382.
- Processed corpus file records: 159,164.
- Runtime PostgreSQL papers: 159,187.
- Runtime RAG chunks: 367,773.
- Runtime chunk embeddings: 367,773.
- Runtime paper embeddings: 159,135.
- Abstract coverage: 140,183 records, 83.22%.
- Full-text field coverage: 15,144 records, 8.99%.
- Title self-retrieval: recall@10 0.985, MRR@10 0.9583.
- Cross-lingual relevance@5: 1.0.
- Trend backtest Pearson: 0.9756.
- Recommendation mean semantic similarity: 0.8918.
- Backend automated tests: 98 passing when run in the project environment.

## Report Polish Gates

- [x] Delivery note, project report, and data report distinguish analysis,
  processed-corpus, runtime, and evaluation metric scopes.
- [x] Project report opens the results chapter with a visible metric box.
- [x] Project report includes a differentiated capability comparison matrix.
- [x] Project report includes a real `verify_claim` example.
- [x] Data report summary closes the social, economic, and technical innovation
  loop.
- [x] Data report and project report use aligned social/economic value framing.
- [x] Format checklist is filled, not left as an abstract recommendation list.
