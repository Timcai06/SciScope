import csv
import json
from pathlib import Path
from typing import Any

from data_pipeline.normalize import normalize_paper


def load_papers(path: str | Path) -> list[dict[str, Any]]:
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
    return [normalize_paper(record) for record in records]
