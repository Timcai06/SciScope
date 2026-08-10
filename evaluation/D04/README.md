# D04 Wave 0 automated silver evidence

This directory defines the reproducible, non-semantic D04 alternative when an
independent 20-paper expert blind review is unavailable. It has no gold labels
and is not an expert evaluation dataset.

`run_silver_consistency_eval` consumes one controlled batch of:

- D02 `traceable/chunks.jsonl`;
- D03 `structured/structured.jsonl` produced from those chunks.

It writes `silver_consistency_report.json`. `technical_gate_pass` is true only
when the D03 output can be deterministically regenerated from the supplied D02
chunks and every extracted field maps exactly through
`chunk_uid -> locator -> text[start:end] == evidence.sentence`.

The report deliberately sets:

- `evidence_level` to `L2_automated_silver_reproducibility_and_provenance_only`;
- `semantic_correctness_claimed` to `false`;
- `external_expert_gate_remaining` to `true`.

It must not be reported as a semantic correctness score, human gold standard,
or external proof. D04 can only receive its overall PASS after the remaining
external gate: a qualified, independent reviewer completes stage-A blind
annotation and stage-B adjudication on 20 license-clear original papers.

The end-to-end invocation is covered by
`backend/tests/test_extraction_eval.py::test_run_silver_consistency_eval_end_to_end`.
