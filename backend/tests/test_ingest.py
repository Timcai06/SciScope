from data_pipeline.sample_data import sample_papers_path


def test_sample_data_exists():
    path = sample_papers_path()
    assert path.exists()
    assert path.name == "papers.sample.json"
