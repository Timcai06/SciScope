"""Offline evaluation of the recommendation model.

维护指标口径:
- 随机抽样 `sample` 篇种子论文，取每篇前 `limit` 条推荐，统计同域/共享关键词等代理指标。
- `same_field_rate = 同域推荐数 / 总推荐数`。
- `shared_keyword_rate = 至少共享 1 个关键词的推荐数 / 总推荐数`（字段 `shared_keywords` 为真值）。
- `mean_semantic_similarity = 推荐语义相似度平均值`，用于辅助判断 embedding 一致性，不代替人工标签。
- 本函数使用 `recommend_service` 返回结果中的字段作为真值，属于离线一致性检验，不构成推荐系统最终业务 KPI。

数据假设:
- 采用 `paper_embeddings ⋈ papers` 的论文池；若某篇种子未能返回推荐将被计入 `seeds_sampled`，
  但不计入 `total_recommendations`。
- field / keyword 字段取决于上游抓取与入库完整性；空字段会降低同域和共享关键词命中率的可比性。
- 通过随机种子 `seed` 保证复现性；不同数据库快照下样本会随时间变更。
"""

from __future__ import annotations

import argparse
import json
import os
import random

from backend.app.services import recommend_service

DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")


def run(dsn: str, sample: int, seed: int, limit: int) -> dict:
    import psycopg

    os.environ.setdefault("SCISCOPE_DB_DSN", dsn)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT coalesce(p.metadata->>'paper_id', p.source_id) AS paper_id, p.paper_uid, p.field
            FROM paper_embeddings pe JOIN papers p ON p.paper_uid = pe.paper_uid
            """
        )
        rows = cur.fetchall()
        seed_field = {r[1]: r[2] for r in rows}

    random.Random(seed).shuffle(rows)
    picked = rows[:sample]

    total_recs = same_field = shared_kw = 0
    sims = []
    seeds_with_recs = 0
    for paper_id, seed_uid, field in picked:
        recs = recommend_service.recommend(paper_id, limit=limit)
        if not recs:
            continue
        seeds_with_recs += 1
        for r in recs:
            total_recs += 1
            if r.field == field:
                same_field += 1
            if r.shared_keywords:
                shared_kw += 1
            sims.append(r.semantic_similarity)
    # 注: 指标分母是 total_recommendations；当推荐为空时会保留 0 值以避免除零，便于脚本稳定输出但不代表“无效模型”。

    return {
        "seeds_sampled": len(picked),
        "seeds_with_recs": seeds_with_recs,
        "total_recommendations": total_recs,
        "same_field_rate": round(same_field / total_recs, 4) if total_recs else 0.0,
        "shared_keyword_rate": round(shared_kw / total_recs, 4) if total_recs else 0.0,
        "mean_semantic_similarity": round(sum(sims) / len(sims), 4) if sims else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline recommendation evaluation")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run(args.dsn, args.sample, args.seed, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
