"""Topic-relevance eval: for a fixed query set, check whether top-k results'
titles contain any expected topic term.

维护口径说明:
- 固定的中英文查询清单（QUERIES）作为离线 smoke test，检查每条查询在前 k 条结果中是否存在任一“期望主题词”。
- `precision_any@k = 通过的查询数 / 查询总数`；这里的“通过”定义为任一 result.title 命中任一预期 term。
- 命中依据是子字符串匹配（title.lower() 中是否包含 term），不做分词、同义词扩展、实体标准化。
- 与检索模型真实相关性分数无直接一致性保证，仅用于可比对回归与最低门槛监测。

数据假设:
- 仅依赖当前代码中的 CURATED 查询项（15 个查询），无外部标注文件。
- `retrieval_service.search(q, limit)` 可稳定返回可解析的 title（字段缺失时可能为 None）。
- 输入为人工维护的主题词映射，中文概念覆盖不完整时会放宽地表现为命中率下界，需结合检索报告共同解读。
"""
from __future__ import annotations
import json, os

# (query, [expected terms any of which should appear in a relevant title);
# terms are evaluated as lowercase substring probes against lowercased result title。
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
    # 注: 指标仅反映当前清单下“是否出现至少一个主题词”的二元覆盖，不代表检索质量的完整 PR/Recall 曲线。
    return {"queries": len(QUERIES), "limit": limit, "precision_any@k": round(hit/len(QUERIES),3), "detail": per}

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
