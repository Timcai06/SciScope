from pathlib import Path


def sample_papers_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "sample" / "papers.sample.json"
