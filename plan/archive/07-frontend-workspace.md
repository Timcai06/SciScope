# Frontend Research Workspace Plan

## 1. Product Direction

The frontend should feel like a serious research intelligence workspace, not a demo dashboard or a generic chat page.

The first screen should expose real corpus insight:

- corpus scale.
- year range.
- field distribution.
- rising keywords.
- author collaboration communities.
- active topics.
- a research question entry point.

## 2. Navigation

Primary views:

- Overview.
- Ask.
- Trends.
- Graph.
- Recommend.
- Report Studio.

## 3. View Design

### Overview

Purpose:

- show the global state of the corpus.
- provide entry points into trends, graph, and QA.

Data:

- total papers.
- field distribution.
- publication trend.
- top keywords.
- top authors.
- recent hot topics.

### Ask

Purpose:

- evidence-grounded literature QA.

UI:

- question input.
- answer panel.
- evidence cards.
- cited papers.
- retrieval diagnostics.

### Trends

Purpose:

- show keyword and topic evolution.

UI:

- keyword search.
- time series chart.
- burst keyword ranking.
- topic trend table.
- representative papers.

### Graph

Purpose:

- inspect author collaboration, keyword co-occurrence, and paper-topic relations.

UI:

- graph canvas.
- filter controls.
- node detail panel.
- path explanation.

### Recommend

Purpose:

- recommend papers by research interest, seed paper, topic, or keyword.

UI:

- seed input.
- recommendation list.
- explanation factors.
- save-to-report action.

### Report Studio

Purpose:

- assemble analysis insights into a report draft.

UI:

- selected charts.
- saved evidence.
- generated sections.
- export status.

## 4. Technical Stack

Current:

- Next.js.
- TypeScript.
- Tailwind CSS.
- TanStack Query.
- ECharts.
- Framer Motion.
- Zustand.

May add later:

- Cytoscape.js for graph views.
- shadcn/ui only if it accelerates polished controls.

## 5. Design Rules

- No landing page.
- First viewport must be the research workspace.
- Charts and evidence are the primary visual objects.
- Every AI answer must show evidence.
- Avoid decorative-only visuals.
- Keep dense information readable.
- Do not let AI Infra dominate the user interface.

## 6. Acceptance

Accepted when:

- Frontend uses real backend APIs, not static mock data.
- Overview, Ask, Trends, Graph, and Recommend each display meaningful corpus-backed data.
- User can start from a question and navigate to evidence, trends, graph, and recommendations.
- `npm run typecheck` and `npm run build` pass.
