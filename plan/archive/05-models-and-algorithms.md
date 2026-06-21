# Models and Algorithms Plan

## 1. Model Definition

The contest asks for a "research agent model". In SciScope, this is not only a large language model. It is a package of:

- Python code.
- processed data assets.
- FTS and vector indices.
- topic model files.
- trend prediction files.
- recommendation model files.
- graph files.
- LLM provider configuration.

The LLM is the reasoning and generation layer. Corpus-specific intelligence comes from reproducible models and indices.

## 2. Retrieval Model

Components:

- chunk generation from title, abstract, keywords, and partial full text.
- lexical retrieval using SQLite FTS5 or BM25.
- vector retrieval using FAISS or LanceDB.
- reciprocal rank fusion.
- optional reranking later.

Outputs:

```text
indices/fts/
indices/vector/
data/processed/chunks.parquet
```

Acceptance:

- `/api/chat` can retrieve evidence from the real corpus.
- Every answer includes paper title, year, authors, and snippet.

## 3. Topic Model

Candidate approaches:

- embedding clustering.
- BERTopic if dependency cost is acceptable.
- simple TF-IDF + clustering fallback for fast local iteration.

Outputs:

```text
models/topics/topic_model.json
models/topics/paper_topics.parquet
models/topics/topic_keywords.csv
```

Acceptance:

- Each paper has a topic assignment.
- Each topic has readable keywords and representative papers.
- Topic-year trend can be computed.

## 4. Trend Model

Features:

- keyword frequency by year.
- topic frequency by year.
- recent growth rate.
- acceleration score.
- burst score.
- stability score.
- evidence density.

Outputs:

```text
models/trends/hot_keywords.csv
models/trends/topic_trends.csv
models/trends/trend_scores.json
```

Acceptance:

- `/api/trends` returns time series, hotspot ranking, and uncertainty notes.
- Report assets use the same trend files.

## 5. Recommendation Model

Signals:

- semantic similarity.
- keyword overlap.
- topic similarity.
- recency.
- author relationship.
- citation count if available.

Outputs:

```text
models/recommend/recommendation_features.parquet
models/recommend/paper_similarity.index
```

Acceptance:

- `/api/recommend` returns ranked papers.
- Each recommendation includes explanation factors.

## 6. Graph Model

Graphs:

- author collaboration graph.
- keyword co-occurrence graph.
- paper-topic graph.

Implementation:

- Use NetworkX for computation.
- Export frontend-friendly JSON.
- Store graph metrics separately for API filtering.

Outputs:

```text
graphs/author_graph.json
graphs/keyword_graph.json
graphs/paper_topic_graph.json
graphs/graph_metrics.json
```

Acceptance:

- `/api/graph` supports author, keyword, topic, and paper-centered queries.
- Graph edges are typed and not confused with inferred relations.

## 7. LLM Provider Strategy

Providers:

- Mock provider for tests.
- Local OpenAI-compatible provider for vLLM/LM Studio.
- DeepSeek provider for final high-quality generation.

Rules:

- The LLM cannot answer without local evidence for corpus-specific claims.
- DeepSeek improves language quality and reasoning, but retrieval evidence remains local and auditable.
