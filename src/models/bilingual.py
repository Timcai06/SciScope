"""Chinese->English research-term expansion for cross-lingual retrieval.

Short Chinese queries make the multilingual embedder retrieve by *language*
(Chinese-titled papers) rather than topic. Appending the English equivalent of
known research terms anchors retrieval to the (mostly English) corpus topics.
"""

from __future__ import annotations

# Curated CN -> EN research terms (ML / CS / NLP / CV / bio / materials / physics).
CN_EN = {
    "大语言模型": "large language model llm",
    "语言模型": "language model",
    "扩散模型": "diffusion model",
    "生成模型": "generative model",
    "强化学习": "reinforcement learning",
    "深度学习": "deep learning",
    "机器学习": "machine learning",
    "迁移学习": "transfer learning",
    "联邦学习": "federated learning",
    "对比学习": "contrastive learning",
    "自监督": "self-supervised learning",
    "图神经网络": "graph neural network gnn",
    "卷积神经网络": "convolutional neural network cnn",
    "神经网络": "neural network",
    "注意力机制": "attention mechanism",
    "变换器": "transformer",
    "计算机视觉": "computer vision",
    "目标检测": "object detection",
    "语义分割": "semantic segmentation",
    "图像分类": "image classification",
    "图像分割": "image segmentation",
    "图像生成": "image generation",
    "自然语言处理": "natural language processing nlp",
    "机器翻译": "machine translation",
    "文本生成": "text generation",
    "问答系统": "question answering",
    "检索增强生成": "retrieval augmented generation rag",
    "知识图谱": "knowledge graph",
    "知识图谱补全": "knowledge graph completion",
    "推荐系统": "recommender system recommendation",
    "推荐算法": "recommendation algorithm",
    "异常检测": "anomaly detection",
    "时间序列": "time series",
    "因果推断": "causal inference",
    "可解释": "explainable interpretability",
    "联邦": "federated",
    "量子计算": "quantum computing",
    "量子": "quantum",
    "蛋白质结构预测": "protein structure prediction",
    "蛋白质": "protein",
    "基因": "gene genomic",
    "药物发现": "drug discovery",
    "新药": "drug discovery",
    "疫苗": "vaccine",
    "新冠": "covid sars-cov-2",
    "癌症": "cancer tumor",
    "单细胞": "single cell",
    "锂电池": "lithium battery",
    "电池": "battery",
    "太阳能电池": "solar cell photovoltaic",
    "钙钛矿": "perovskite",
    "催化": "catalysis catalyst",
    "材料发现": "materials discovery",
    "半导体": "semiconductor",
    "超导": "superconductor",
    "纳米": "nano",
}


def expand_bilingual(query: str) -> str:
    """Append English equivalents of any known Chinese terms in the query."""
    if not query or not any("一" <= ch <= "鿿" for ch in query):
        return query
    additions = []
    seen = set()
    # Longest terms first so '大语言模型' wins over '语言模型'.
    for cn in sorted(CN_EN, key=len, reverse=True):
        if cn in query and cn not in seen:
            additions.append(CN_EN[cn])
            seen.add(cn)
    if not additions:
        return query
    return query + " " + " ".join(additions)
