"""Topic-relevance eval: for a fixed query set, check whether top-k results'
titles contain any expected topic term. Measures precision@k of retrieval
relevance (complements self-retrieval recall). No manual labels beyond the
small curated set below.
"""
from __future__ import annotations
import json, os

# (query, [expected English topic terms any of which should appear in a relevant title])
QUERIES = [
    ("大语言模型", ["language model", "llm", "gpt"]),
    ("计算机视觉目标检测", ["object detection", "detection", "computer vision", "yolo", "image"]),
    ("扩散模型", ["diffusion", "generative", "score-based"]),
    ("蛋白质结构预测", ["protein", "structure", "folding"]),
    ("联邦学习", ["federated"]),
    ("知识图谱", ["knowledge graph", "kg"]),
    ("强化学习", ["reinforcement learning", "policy", "reward", "rl"]),
    ("量子计算", ["quantum"]),
    ("图神经网络", ["graph neural", "gnn", "graph network"]),
    ("目标检测", ["detection", "detector", "yolo"]),
    ("机器翻译", ["machine translation", "translation", "nmt"]),
    ("推荐系统", ["recommend", "recommendation", "collaborative filtering"]),
    ("语义分割", ["segmentation", "semantic"]),
    ("药物发现", ["drug", "molecul", "compound"]),
    ("太阳能电池", ["solar", "photovoltaic", "perovskite"]),
]

def run(limit: int = 5) -> dict:
    from backend.app.services import retrieval_service as rs
    hit = 0; per = []
    for q, terms in QUERIES:
        res = rs.search(q, limit=limit)
        ok = any(any(t in (r.title or "").lower() for t in terms) for r in res)
        hit += ok
        per.append({"q": q, "relevant_in_topk": ok, "top": res[0].title[:50] if res else None})
    return {"queries": len(QUERIES), "limit": limit, "precision_any@k": round(hit/len(QUERIES),3), "detail": per}

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
