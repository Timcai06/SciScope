"""Run the G04b recommendation bake-off on an existing full database.

Four baselines share the same deterministic seed set:

* ``popularity_proxy``: global metadata-richness proxy.  The corpus has no
  citation/view/save signal, so this MUST NOT be described as real popularity.
* ``keyword_tfidf``: IDF-weighted overlap over normalized paper keywords.
* ``dense``: direct nearest neighbours from ``paper_embeddings``.
* ``current``: the production semantic/keyword/author/recency + MMR service.

All output metrics are automatic proxies.  Human/expert value remains a
separate blocked gate.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Any, Callable

from evaluation.recommend_bakeoff import EvalPaper, aggregate_baseline


BASELINES = ("popularity_proxy", "keyword_tfidf", "dense", "current")
DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _vector(value: Any) -> tuple[float, ...]:
    if value is None:
        return ()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return tuple(float(item) for item in value)


def _sample_manifest(ordered_uids: list[str], *, sample: int, seed: int) -> dict[str, Any]:
    """Freeze the candidate pool fingerprint and exact replayable seed set."""

    fingerprint = hashlib.sha256()
    for paper_uid in ordered_uids:
        fingerprint.update(paper_uid.encode("utf-8"))
        fingerprint.update(b"\0")
    shuffled = list(ordered_uids)
    random.Random(seed).shuffle(shuffled)
    return {
        "candidate_count": len(ordered_uids),
        "candidate_uid_sha256": fingerprint.hexdigest(),
        "seed_uids": shuffled[:sample],
    }


def _sample_seeds(cur, *, sample: int, seed: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT p.paper_uid
        FROM paper_embeddings pe JOIN papers p ON p.paper_uid = pe.paper_uid
        ORDER BY p.paper_uid
        """
    )
    rows = [row[0] for row in cur.fetchall()]
    return _sample_manifest(rows, sample=sample, seed=seed)


def _corpus_profile(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
          (SELECT count(*) FROM papers),
          (SELECT count(*) FROM paper_embeddings),
          (SELECT count(DISTINCT embedding_model) FROM paper_embeddings),
          (SELECT min(embedding_model) FROM paper_embeddings)
        """
    )
    papers, embeddings, model_count, model = cur.fetchone()
    cur.execute(
        """
        SELECT max(
          ln(1 + greatest(coalesce((metadata->>'authors_count')::int, 0), 0)) +
          ln(1 + greatest(coalesce((metadata->>'keywords_count')::int, 0), 0))
        )
        FROM papers p JOIN paper_embeddings pe ON pe.paper_uid = p.paper_uid
        """
    )
    max_popularity = float(cur.fetchone()[0] or 1.0)
    return {
        "papers": int(papers),
        "paper_embeddings": int(embeddings),
        "embedding_model_count": int(model_count),
        "embedding_model": model,
        "max_metadata_richness": max_popularity,
    }


def _hydrate(cur, uids: list[str], *, max_popularity: float) -> dict[str, EvalPaper]:
    unique = list(dict.fromkeys(uids))
    if not unique:
        return {}
    cur.execute(
        """
        SELECT p.paper_uid, coalesce(p.metadata->>'paper_id', p.source_id), p.field,
               pe.embedding,
               ln(1 + greatest(coalesce((p.metadata->>'authors_count')::int, 0), 0)) +
               ln(1 + greatest(coalesce((p.metadata->>'keywords_count')::int, 0), 0))
        FROM papers p JOIN paper_embeddings pe ON pe.paper_uid = p.paper_uid
        WHERE p.paper_uid = ANY(%s)
        """,
        (unique,),
    )
    rows = cur.fetchall()
    cur.execute(
        """
        SELECT pk.paper_uid, k.normalized_keyword
        FROM paper_keywords pk JOIN keywords k ON k.keyword_uid = pk.keyword_uid
        WHERE pk.paper_uid = ANY(%s)
        """,
        (unique,),
    )
    keywords: dict[str, set[str]] = {}
    for paper_uid, keyword in cur.fetchall():
        keywords.setdefault(paper_uid, set()).add(keyword)
    return {
        row[0]: EvalPaper(
            paper_uid=row[0],
            paper_id=str(row[1]),
            field=str(row[2] or "unknown"),
            keywords=frozenset(keywords.get(row[0], set())),
            embedding=_vector(row[3]),
            popularity_proxy=min(1.0, float(row[4] or 0.0) / (max_popularity or 1.0)),
        )
        for row in rows
    }


def _popularity_uids(cur, seed_uid: str, *, limit: int) -> list[str]:
    cur.execute(
        """
        SELECT p.paper_uid
        FROM papers p JOIN paper_embeddings pe ON pe.paper_uid = p.paper_uid
        WHERE p.paper_uid <> %s
        ORDER BY
          ln(1 + greatest(coalesce((p.metadata->>'authors_count')::int, 0), 0)) +
          ln(1 + greatest(coalesce((p.metadata->>'keywords_count')::int, 0), 0)) DESC,
          p.paper_uid
        LIMIT %s
        """,
        (seed_uid, limit),
    )
    return [row[0] for row in cur.fetchall()]


def _keyword_tfidf_uids(cur, seed_uid: str, *, corpus_size: int, limit: int) -> list[str]:
    cur.execute(
        """
        WITH seed_keywords AS (
          SELECT keyword_uid FROM paper_keywords WHERE paper_uid = %(seed)s
        ), keyword_df AS (
          SELECT pk.keyword_uid, count(*) AS df
          FROM paper_keywords pk JOIN seed_keywords sk USING (keyword_uid)
          GROUP BY pk.keyword_uid
        )
        SELECT pk.paper_uid,
               sum(ln((%(corpus_size)s + 1.0) / (keyword_df.df + 1.0)) + 1.0) AS score
        FROM paper_keywords pk
        JOIN keyword_df USING (keyword_uid)
        JOIN paper_embeddings pe ON pe.paper_uid = pk.paper_uid
        WHERE pk.paper_uid <> %(seed)s
        GROUP BY pk.paper_uid
        ORDER BY score DESC, pk.paper_uid
        LIMIT %(limit)s
        """,
        {"seed": seed_uid, "corpus_size": corpus_size, "limit": limit},
    )
    return [row[0] for row in cur.fetchall()]


def _dense_uids(cur, seed_uid: str, *, limit: int) -> list[str]:
    cur.execute("SELECT embedding FROM paper_embeddings WHERE paper_uid = %s", (seed_uid,))
    row = cur.fetchone()
    if not row:
        return []
    cur.execute(
        """
        SELECT paper_uid
        FROM paper_embeddings
        WHERE paper_uid <> %s
        ORDER BY embedding <=> %s
        LIMIT %s
        """,
        (seed_uid, row[0], limit),
    )
    return [candidate[0] for candidate in cur.fetchall()]


def _current_uids(cur, seed: EvalPaper, *, limit: int) -> list[str]:
    from backend.app.services import recommend_service

    recs = recommend_service.recommend(seed.paper_id, limit=limit)
    ids = [rec.paper_id for rec in recs]
    if not ids:
        return []
    cur.execute(
        """
        SELECT paper_uid, coalesce(metadata->>'paper_id', source_id), source_id
        FROM papers
        WHERE paper_uid = ANY(%s) OR source_id = ANY(%s) OR metadata->>'paper_id' = ANY(%s)
        """,
        (ids, ids, ids),
    )
    aliases: dict[str, str] = {}
    for paper_uid, paper_id, source_id in cur.fetchall():
        aliases[paper_uid] = paper_uid
        aliases[str(paper_id)] = paper_uid
        aliases[str(source_id)] = paper_uid
    return [aliases[item] for item in ids if item in aliases and aliases[item] != seed.paper_uid]


def _evaluate_one(
    cur,
    *,
    name: str,
    seeds: list[EvalPaper],
    ranker: Callable[[EvalPaper], list[str]],
    max_popularity: float,
) -> dict:
    recommendations: dict[str, list[EvalPaper]] = {}
    latencies: list[float] = []
    failures: list[dict[str, str]] = []
    for seed in seeds:
        started = time.perf_counter()
        try:
            uids = list(dict.fromkeys(ranker(seed)))
            hydrated = _hydrate(cur, uids, max_popularity=max_popularity)
            recommendations[seed.paper_uid] = [hydrated[uid] for uid in uids if uid in hydrated]
            if not recommendations[seed.paper_uid]:
                failures.append({"paper_id": seed.paper_id, "reason": "no_recommendations"})
        except Exception as exc:  # fail one seed without turning the run into silent success
            recommendations[seed.paper_uid] = []
            # Do not serialize driver messages: they may contain host or DSN details.
            failures.append({"paper_id": seed.paper_id, "reason": type(exc).__name__})
        latencies.append((time.perf_counter() - started) * 1000.0)
    return aggregate_baseline(
        name=name,
        seeds=seeds,
        recommendations=recommendations,
        latency_ms=latencies,
        failures=failures,
    )


def run(
    dsn: str,
    *,
    sample: int,
    seed: int,
    limit: int,
    replay_seed_uids: list[str] | None = None,
) -> dict[str, Any]:
    import psycopg
    from pgvector.psycopg import register_vector

    os.environ["SCISCOPE_DB_DSN"] = dsn
    # Autocommit keeps one failed read from poisoning later seeds with an aborted
    # transaction.  Every statement in this evaluator is read-only.
    with psycopg.connect(dsn, autocommit=True) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            profile = _corpus_profile(cur)
            sample_manifest = _sample_seeds(cur, sample=sample, seed=seed)
            seed_uids = list(replay_seed_uids or sample_manifest["seed_uids"])
            sample_manifest["seed_uids"] = seed_uids
            sample_manifest["selection_mode"] = "replay" if replay_seed_uids else "seeded_shuffle"
            seed_map = _hydrate(cur, seed_uids, max_popularity=profile["max_metadata_richness"])
            missing_seeds = [uid for uid in seed_uids if uid not in seed_map]
            if missing_seeds:
                raise RuntimeError(
                    f"seed replay does not match this database snapshot: {len(missing_seeds)} missing"
                )
            seeds = [seed_map[uid] for uid in seed_uids if uid in seed_map]
            rankers: dict[str, Callable[[EvalPaper], list[str]]] = {
                "popularity_proxy": lambda item: _popularity_uids(cur, item.paper_uid, limit=limit),
                "keyword_tfidf": lambda item: _keyword_tfidf_uids(
                    cur, item.paper_uid, corpus_size=profile["papers"], limit=limit
                ),
                "dense": lambda item: _dense_uids(cur, item.paper_uid, limit=limit),
                "current": lambda item: _current_uids(cur, item, limit=limit),
            }
            results = [
                _evaluate_one(
                    cur,
                    name=name,
                    seeds=seeds,
                    ranker=rankers[name],
                    max_popularity=profile["max_metadata_richness"],
                )
                for name in BASELINES
            ]

    return {
        "schema_version": "recommend-bakeoff/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": _commit(),
        "parameters": {"sample": sample, "seed": seed, "limit": limit},
        "sample_manifest": sample_manifest,
        "corpus": profile,
        "baseline_definitions": {
            "popularity_proxy": "global authors_count + keywords_count metadata-richness proxy; no citations/views/saves exist",
            "keyword_tfidf": "IDF-weighted overlap of normalized keywords",
            "dense": "direct pgvector cosine nearest neighbours",
            "current": "production semantic + keyword + author + recency fusion with MMR",
        },
        "latency_scope": "per-seed wall clock including each baseline native ranking and evaluator hydration",
        "results": results,
        "claim_boundary": {
            "automatic_proxy_metrics_only": True,
            "winner_declared": False,
            "human_or_expert_value_status": "BLOCKED",
            "note": "No automatic metric proves researcher satisfaction, novelty discovery, or efficiency improvement.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    rows = [
        "# G04b recommendation bake-off",
        "",
        "> Automatic proxy evaluation only; user/expert value remains BLOCKED.",
        "",
        "| baseline | coverage | same field | shared keyword | semantic | diversity | novelty proxy | p50 ms | p95 ms | failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        latency = item["latency_ms"]
        rows.append(
            "| {baseline} | {coverage} | {same} | {shared} | {semantic} | {diversity} | {novelty} | {p50} | {p95} | {failures} |".format(
                baseline=item["baseline"],
                coverage=_display(item["coverage"]),
                same=_display(item["same_field_rate"]),
                shared=_display(item["shared_keyword_rate"]),
                semantic=_display(item["mean_seed_semantic_similarity"]),
                diversity=_display(item["mean_intra_list_diversity"]),
                novelty=_display(item["mean_metadata_novelty_proxy"]),
                p50=_display(latency["p50"]),
                p95=_display(latency["p95"]),
                failures=item["failure_count"],
            )
        )
    rows.extend(
        [
            "",
            "## Boundaries",
            "",
            "- `popularity_proxy` is metadata richness, not citation/view/save popularity.",
            "- Relevance, diversity and novelty are automatic proxies without human labels.",
            "- This table declares no winning recommender and no researcher-efficiency improvement.",
            "",
        ]
    )
    return "\n".join(rows)


def _display(value: Any) -> str:
    return "n/a" if value is None else str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="G04b multi-baseline recommendation evaluation")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("output/eval/recommend_bakeoff.json"))
    parser.add_argument(
        "--replay-from",
        type=Path,
        help="Prior recommend-bakeoff JSON whose sample_manifest.seed_uids must be replayed",
    )
    args = parser.parse_args()
    replay_seed_uids = None
    if args.replay_from:
        prior = json.loads(args.replay_from.read_text(encoding="utf-8"))
        replay_seed_uids = list(prior["sample_manifest"]["seed_uids"])
        if args.sample != len(replay_seed_uids):
            raise SystemExit(
                f"--sample={args.sample} does not match replay manifest size {len(replay_seed_uids)}"
            )
    report = run(
        args.dsn,
        sample=args.sample,
        seed=args.seed,
        limit=args.limit,
        replay_seed_uids=replay_seed_uids,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
