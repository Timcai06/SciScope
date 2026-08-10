# G04b recommendation bake-off

> Automatic proxy evaluation only; user/expert value remains BLOCKED.

| baseline | coverage | same field | shared keyword | semantic | diversity | novelty proxy | p50 ms | p95 ms | failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| popularity_proxy | 1.0 | 0.338 | 0.052 | 0.843097 | 0.158853 | 0.027143 | 68.53 | 69.037 | 0 |
| keyword_tfidf | 0.73 | 0.730028 | 1.0 | 0.926279 | 0.077933 | 0.517354 | 48.404 | 156.018 | 27 |
| dense | 1.0 | 0.694 | 0.508 | 0.933225 | 0.06821 | 0.580979 | 4.154 | 10.152 | 0 |
| current | 1.0 | 0.718 | 0.628 | 0.926293 | 0.082263 | 0.588524 | 100.623 | 128.113 | 0 |

## Boundaries

- `popularity_proxy` is metadata richness, not citation/view/save popularity.
- Relevance, diversity and novelty are automatic proxies without human labels.
- This table declares no winning recommender and no researcher-efficiency improvement.
