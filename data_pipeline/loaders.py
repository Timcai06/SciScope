import csv
import json
from pathlib import Path
from typing import Any

from data_pipeline.models import Paper
from data_pipeline.normalize import normalize_paper


"""Load raw paper records from supported source files and normalize+validate them.

This module is the first stop of the backend pipeline:
JSON/CSV ingestion -> normalization -> pydantic shape validation.
Keep this boundary narrow so upstream changes do not leak into downstream models.
"""


def _validate_paper_schema(record: dict[str, Any]) -> dict[str, Any]:
    # Keep output as a plain dict that already matches the Paper schema.
    # This gives downstream stages a stable contract regardless of pydantic v1/v2.
    if hasattr(Paper, "model_validate"):
        return Paper.model_validate(record).model_dump()
    return Paper.parse_obj(record).dict()


def load_papers(path: str | Path) -> list[dict[str, Any]]:
    # File readers preserve raw payload shape and type per source format before normalization.
    # For each record we explicitly normalize first, then enforce the model contract.
    source = Path(path)
    if source.suffix.lower() == ".json":
        records = json.loads(source.read_text(encoding="utf-8"))
    elif source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8", newline="") as handle:
            records = list(csv.DictReader(handle))
    else:
        raise ValueError(f"Unsupported paper data format: {source.suffix}")
    if not isinstance(records, list):
        raise ValueError("Paper data must be a list of records")
    return [_validate_paper_schema(normalize_paper(record)) for record in records]
