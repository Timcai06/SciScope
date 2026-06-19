# Data Assets and Schema Plan

## 1. Canonical Paper Schema

Each normalized paper record should contain:

```text
paper_id
source
source_id
doi
title
abstract
authors
author_ids
institutions
year
publication_date
keywords
field
topics
venue
url
full_text
citation_count
raw_ref
```

Required minimum fields:

- paper_id
- title
- abstract
- authors
- year
- keywords or topics
- field

## 2. Processed Asset Layout

```text
data/processed/
  papers.parquet
  authors.parquet
  paper_authors.parquet
  keywords.parquet
  paper_keywords.parquet
  chunks.parquet
  keyword_year.csv
  data_quality.json
```

## 3. Graph Asset Layout

```text
graphs/
  author_graph.json
  keyword_graph.json
  paper_topic_graph.json
  graph_metrics.json
```

Graph node types:

- paper
- author
- keyword
- topic
- institution
- field

Graph edge types:

- coauthor
- paper-author
- paper-keyword
- paper-topic
- keyword-cooccurrence
- author-institution

## 4. Model and Index Layout

```text
indices/
  fts/
  vector/

models/
  topics/
    topic_model.json
    paper_topics.parquet
  trends/
    hot_keywords.csv
    topic_trends.csv
    trend_scores.json
  recommend/
    paper_similarity.index
    recommendation_features.parquet
```

## 5. PostgreSQL Tables

PostgreSQL should be introduced after Parquet outputs are stable.

Tables:

- papers
- authors
- paper_authors
- keywords
- paper_keywords
- topics
- paper_topics
- chunks
- crawl_runs
- analysis_runs

Recommended indexes:

- papers(year)
- papers(field)
- papers(doi)
- authors(name)
- keywords(keyword)
- paper_authors(paper_id)
- paper_keywords(keyword_id)
- chunks(paper_id)

## 6. Data Quality Metrics

Track:

- record count.
- duplicate count.
- title coverage.
- abstract coverage.
- author coverage.
- year coverage.
- keyword/topic coverage.
- field coverage.
- source distribution.
- year distribution.

## 7. Acceptance

Accepted when:

- `make normalize` generates all required processed assets.
- Data quality report is generated.
- PostgreSQL load can be rerun idempotently.
- Backend APIs can switch from sample JSON to processed assets without changing frontend code.
