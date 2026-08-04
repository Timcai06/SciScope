"""Stance & controversy layer (L3 evidence core).

This package is the home of the evidence-side service layer: stance judgement
persistence, disputed-claim reads, and — as the L3 roadmap lands — evidence
sentence location, calibration/rejection and qualification-aware judgement.

- `store.py`: `claim_evidence_stance` persistence and the `contradictions`
  view reads (fail-open), the seed of the 科学争议地图.
"""

from . import store  # noqa: F401

__all__ = ["store"]
