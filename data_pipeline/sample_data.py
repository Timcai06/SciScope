from pathlib import Path


def sample_papers_path() -> Path:
    # Single shared sample fixture path used by quick-start commands and tests.
    return Path(__file__).resolve().parents[1] / "data" / "sample" / "papers.sample.json"
