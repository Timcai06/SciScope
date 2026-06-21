# Data Acquisition Plan

## 1. Data Sources

Primary source:

- OpenAlex: broad paper metadata, authors, institutions, concepts/topics, publication years, DOI links.

Supplementary sources:

- arXiv: computer science and AI papers.
- PubMed / NCBI E-utilities: biomedical papers.
- Crossref: DOI and publication metadata enrichment.

## 2. Why Not Direct-to-PostgreSQL First

Direct crawling into PostgreSQL is risky at the start because:

- Public APIs return heterogeneous records.
- Crawls can fail, duplicate, or be interrupted.
- Schema will change during early experiments.
- We need raw data retention for reproducibility.
- PostgreSQL should serve stable structured data, not absorb unstable raw crawl responses.

## 3. Harvesting Strategy

Stage sizes:

- Pilot: 500 papers.
- Small corpus: 5k papers.
- Contest sample scale: 10k papers.
- Final scale: 50k papers.

Domain quotas:

```text
computer science: 40%
biomedicine:      35%
materials science:25%
```

The quota can change after field coverage analysis.

## 4. Query Seeds

Computer science:

- large language model
- retrieval augmented generation
- knowledge graph
- graph neural network
- natural language processing
- information retrieval

Biomedicine:

- drug discovery
- biomedical NLP
- protein design
- clinical decision support
- genomics
- molecular property prediction

Materials science:

- materials discovery
- battery materials
- catalyst discovery
- property prediction
- crystal structure prediction
- machine learning materials

## 5. Raw Data Layout

```text
data/raw/
  openalex/
    crawl_runs.jsonl
    works_YYYYMMDD_partNN.jsonl
  arxiv/
    crawl_runs.jsonl
    papers_YYYYMMDD_partNN.jsonl
  pubmed/
    crawl_runs.jsonl
    papers_YYYYMMDD_partNN.jsonl
```

Every raw record should keep:

- source name.
- source record id.
- crawl timestamp.
- query seed.
- raw payload.

## 6. Harvester Modules

```text
src/harvest/
  __init__.py
  openalex_client.py
  arxiv_client.py
  pubmed_client.py
  crossref_client.py
  normalize.py
  dedupe.py
  cli.py
```

## 7. Makefile Targets

```bash
make harvest-sample SOURCE=openalex LIMIT=500
make harvest-all LIMIT=50000
make normalize
make data-quality
```

## 8. Required Safeguards

- Rate limiting per source.
- Retry with exponential backoff.
- Checkpointed pagination cursor.
- User agent or contact email where supported.
- Deduplication by DOI, source id, title hash, and title-year-author heuristic.
- Raw record retention.

## 9. Acceptance

The acquisition pipeline is accepted when:

- A 500-paper pilot can be harvested twice without duplicate processed records.
- The normalized schema covers at least 95% of titles, abstracts, years, and authors.
- Source, query, and crawl metadata are preserved.
- The same commands can scale from 500 to 5k and 10k without code changes.
