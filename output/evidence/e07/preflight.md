# E07 judge-demo preflight

- generated: `2026-08-12T14:08:11.989166+00:00`
- overall: `READY_FOR_HUMAN_REVIEW`

| Check | Status | Detail | Evidence |
|---|---|---|---|
| required-assets | PASS | all required assets exist | `output/evidence/t04, output/evidence/e04, output/pdf` |
| three-online-runs | PASS | 3 runs: HTTP 200, DONE, no error, citations ok | `output/evidence/t04/online/summary.json` |
| recorded-readiness | PASS | DB, retrieval/pgvector and model configured | `output/evidence/t04/online/readyz.json` |
| full-corpus-hardware | PASS | full corpus, complete vectors and RTX 2080 Ti recorded | `output/evidence/t04/runtime/manifest.md` |
| tui-fail-closed-and-retry | PASS | first citation failure retained; recorded retry passed | `output/evidence/t04/tui` |
| offline-and-failure-fallback | PASS | offline fixture and explicit blocked recovery captured | `output/evidence/t04/offline` |
| opencode-mcp-order | PASS | verify_claim(persist=true) precedes disputes resource read; fixture boundary applies | `output/evidence/e04/opencode_run_e04.jsonl` |
| evidence-integrity | PASS | 20 files verified | `output/evidence/t04/SHA256SUMS` |
| technical-video | PENDING | record 60-second submission video and 6-8 minute technical video | `human-owned recording` |
| nontechnical-review | PENDING | a non-project reviewer must complete the timed acceptance form | `human-owned acceptance` |

`READY_FOR_HUMAN_REVIEW` means engineering evidence is complete while video and reviewer acceptance remain pending.
