# Data Analysis Report Plan

## 1. Purpose

The report must prove that SciScope can extract meaningful research insights from a large scientific literature corpus. It should not be a collection of screenshots. Every chart and conclusion must be reproducible from data assets and scripts.

## 2. Report Outputs

Final report artifacts:

```text
reports/
  data_analysis_report.pdf
  data_analysis_report.md
  assets/
    publication_trend.png
    field_distribution.png
    field_year_heatmap.png
    keyword_topk.png
    keyword_evolution.png
    burst_keywords.png
    author_collaboration_network.png
    author_centrality.csv
    topic_trends.png
    trend_predictions.csv
    summary_metrics.json
```

## 3. Required Analyses

### 3.1 Literature Distribution

Questions:

- How many papers are collected per year?
- Which fields are represented?
- Are domains balanced across computer science, biomedicine, and materials science?
- Which venues or sources dominate the corpus?

Outputs:

- year trend line.
- field distribution chart.
- field-year heatmap.
- source distribution table.

### 3.2 Keyword Evolution

Questions:

- Which keywords are most frequent?
- Which keywords grow fastest?
- Which keywords show burst behavior?
- Which keywords bridge multiple fields?

Outputs:

- top keyword bar chart.
- keyword-year matrix.
- burst keyword ranking.
- keyword evolution heatmap.

### 3.3 Author Collaboration Network

Questions:

- Who are the central authors?
- Which collaboration communities exist?
- Which authors connect different communities?
- Are there cross-field collaborations?

Outputs:

- coauthor network graph.
- degree centrality.
- betweenness centrality.
- community assignment.
- top collaboration pairs.

### 3.4 Topic Structure and Evolution

Questions:

- What major research topics exist?
- Which topics are emerging, stable, or declining?
- Which fields share similar topics?

Outputs:

- topic clusters.
- topic keywords.
- representative papers.
- topic trend chart.

### 3.5 Hotspot and Trend Prediction

Questions:

- Which topics are likely to remain hot?
- Which keywords show recent acceleration?
- Which topics have enough evidence density to be trusted?

Outputs:

- hotspot score table.
- trend prediction table.
- uncertainty notes.

## 4. Analysis Code Layout

```text
src/analysis/
  distribution.py
  keywords.py
  collaboration.py
  topics.py
  trends.py
  report_assets.py
```

## 5. Makefile Targets

```bash
make analyze
make report-assets
make report
```

## 6. Acceptance

Accepted when:

- The report can be regenerated from processed assets without manual editing.
- Every major chart has a source CSV/JSON.
- Every conclusion references a computed metric or evidence table.
- The report includes distribution, keyword evolution, author collaboration, topic evolution, and trend prediction.
