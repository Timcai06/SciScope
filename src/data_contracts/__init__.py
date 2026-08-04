"""Shared data contracts for the runtime backend.

This package holds the canonical `Paper` payload model, loaders and
normalization helpers that are consumed by both the backend runtime
(`backend.app`) and the data engineering chain (`src.harvest`), keeping a
single contract between the two worlds.

The production data path is `src.harvest` -> `src.analysis` -> `src.infra`;
this package is the cross-layer contract layer, not a data path itself.
"""
