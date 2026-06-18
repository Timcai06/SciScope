from backend.app.services.analytics_service import build_dashboard_overview
from data_pipeline.analytics import (
    author_collaboration_edges,
    field_distribution,
    keyword_counts,
    publication_trend,
)
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


def _sample_papers():
    return load_papers(sample_papers_path())


def test_publication_trend_counts_sample_years():
    assert publication_trend(_sample_papers()) == [
        {"year": 2020, "count": 1},
        {"year": 2021, "count": 1},
        {"year": 2022, "count": 1},
        {"year": 2023, "count": 1},
        {"year": 2024, "count": 1},
    ]


def test_keyword_counts_returns_limited_most_common_keywords():
    counts = keyword_counts(_sample_papers(), limit=3)

    assert counts == [
        {"keyword": "biomedical literature mining", "count": 1},
        {"keyword": "biomedicine", "count": 1},
        {"keyword": "drug discovery", "count": 1},
    ]


def test_keyword_counts_sorts_ties_by_keyword():
    counts = keyword_counts(
        [
            {"keywords": ["b", "a"]},
            {"keywords": ["b", "a"]},
        ],
        limit=2,
    )

    assert counts == [
        {"keyword": "a", "count": 2},
        {"keyword": "b", "count": 2},
    ]


def test_field_distribution_counts_and_sorts_sample_fields():
    assert field_distribution(_sample_papers()) == [
        {"field": "biomedicine", "count": 2},
        {"field": "computer science", "count": 2},
        {"field": "materials science", "count": 1},
    ]


def test_field_distribution_counts_missing_as_unknown():
    assert field_distribution([{"field": None}, {}]) == [
        {"field": "unknown", "count": 2},
    ]


def test_author_collaboration_edges_counts_sample_coauthors():
    edges = author_collaboration_edges(_sample_papers())

    assert {"source": "Chen Ming", "target": "Li Wei", "weight": 1} in edges
    assert {"source": "Garcia Ana", "target": "Zhang Rui", "weight": 1} in edges


def test_build_dashboard_overview_combines_analytics():
    overview = build_dashboard_overview(_sample_papers())

    assert overview["total_papers"] == 5
    assert overview["year_range"] == {"start": 2020, "end": 2024}
    assert overview["publication_trend"] == publication_trend(_sample_papers())
    assert overview["field_distribution"] == field_distribution(_sample_papers())
    assert overview["top_keywords"] == keyword_counts(_sample_papers(), limit=10)
    assert overview["collaboration_edges"] == author_collaboration_edges(_sample_papers())


def test_dashboard_overview_year_range_empty_when_no_years():
    overview = build_dashboard_overview(
        [{"year": None, "field": "unknown", "keywords": [], "authors": []}]
    )

    assert overview["year_range"] == {"start": None, "end": None}
