# Agent and API Plan

## 1. Product Goal

The SciScope agent should help researchers ask questions, inspect evidence, discover trends, find papers, and query collaboration or topic graphs. It is not a generic chatbot.

## 2. Agentic Workflow

```text
User question
  -> Planner
  -> Retriever
  -> Graph Agent
  -> Trend Agent
  -> Recommendation Agent
  -> Synthesis Agent
  -> Critic
  -> Answer with evidence
```

## 3. Agents

Planner:

- classify intent: QA, trend, recommendation, graph, report, opportunity.
- extract entities, keywords, years, fields, and constraints.

Retriever:

- run lexical and vector search.
- return evidence snippets and retrieval diagnostics.

Graph Agent:

- query author, keyword, paper, and topic graph assets.
- return typed paths and graph metrics.

Trend Agent:

- query keyword and topic time series.
- return growth, burst, and stability metrics.

Recommendation Agent:

- rank papers by semantic, topic, keyword, author, and time signals.
- explain why each paper is recommended.

Synthesis Agent:

- call DeepSeek/local LLM with structured context.
- generate answer, trend explanation, or report section.

Critic:

- check whether claims are supported by evidence.
- reject or downgrade unsupported assertions.

## 4. API Roadmap

Existing:

- `GET /api/ingest/status`
- `GET /api/dashboard/overview`
- `POST /api/chat`

Next:

- `GET /api/papers/search`
- `GET /api/trends`
- `GET /api/topics`
- `GET /api/graph`
- `POST /api/recommend`
- `POST /api/report/draft`

## 5. Response Contracts

Chat response must include:

- answer.
- evidence cards.
- confidence.
- cited paper ids.
- retrieval diagnostics.

Trend response must include:

- series.
- hot keywords/topics.
- growth metrics.
- uncertainty notes.
- representative papers.

Recommendation response must include:

- paper list.
- score.
- explanation factors.
- evidence snippets.

Graph response must include:

- nodes.
- edges.
- node types.
- edge types.
- metrics.

## 6. Backend Module Layout

```text
backend/app/api/
  routes_chat.py
  routes_dashboard.py
  routes_ingest.py
  routes_trends.py
  routes_recommend.py
  routes_graph.py
  routes_papers.py

backend/app/services/
  corpus_service.py
  retrieval_service.py
  trend_service.py
  recommendation_service.py
  graph_service.py
  agent_service.py
  deepseek_provider.py
```

## 7. Acceptance

Accepted when:

- Chat answers use real corpus evidence.
- Trend API returns computed keyword/topic time series.
- Recommendation API returns explained recommendations.
- Graph API returns typed nodes and edges.
- Tests cover normal, empty, and low-evidence cases.
