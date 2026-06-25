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
    # broadened coverage
    "生成对抗网络": "generative adversarial network gan",
    "多模态": "multimodal",
    "预训练": "pretraining pretrained",
    "微调": "fine-tuning",
    "提示工程": "prompt engineering",
    "思维链": "chain of thought reasoning",
    "智能体": "agent autonomous agent",
    "多智能体": "multi-agent",
    "情感分析": "sentiment analysis",
    "命名实体识别": "named entity recognition ner",
    "文本分类": "text classification",
    "聚类": "clustering",
    "降维": "dimensionality reduction",
    "超分辨率": "super resolution",
    "人脸识别": "face recognition",
    "姿态估计": "pose estimation",
    "自动驾驶": "autonomous driving self-driving",
    "语音识别": "speech recognition",
    "脑机接口": "brain computer interface",
    "医学影像": "medical imaging",
    "影像分割": "image segmentation",
    "电子健康记录": "electronic health record ehr",
    "蛋白质设计": "protein design",
    "分子生成": "molecular generation",
    "材料基因组": "materials genome",
    "储能": "energy storage",
    "燃料电池": "fuel cell",
    "气候变化": "climate change",
    "遥感": "remote sensing",
    "区块链": "blockchain",
    "边缘计算": "edge computing",
    "隐私保护": "privacy preserving differential privacy",
    "对抗攻击": "adversarial attack",
}


def expand_bilingual(query: str) -> str:
    """Replace known Chinese research terms with their English equivalents.

    Replacement (not append) avoids two failure modes: the FTS arm AND-failing on
    an unmatchable Chinese token, and the semantic arm being dragged toward
    Chinese-titled papers by the Chinese prefix. Untranslated Chinese is kept and
    handled cross-lingually by the embedder. The English equivalent is inserted
    in-place (or appended when a span does not overlap) so the original intent
    is preserved.
    """
    # 不变量：
    # - 仅当查询确认为中文语境时执行映射，避免将英文查询错误打断。
    # - 使用字典最长匹配，避免“语言模型”覆盖“生成式大语言模型”等子串偏移。
    # - 替换后按空白归一化，保证下游 embedding 输入稳定。
    if not query or not any("一" <= ch <= "鿿" for ch in query):
        return query
    out = query
    additions = []
    # Longest terms first so '大语言模型' wins over '语言模型'.
    for cn in sorted(CN_EN, key=len, reverse=True):
        if cn in out:
            out = out.replace(cn, " " + CN_EN[cn] + " ")
            additions.append(CN_EN[cn])
    if not additions:
        return query
    # additions 保留为变换发生性的语义锚点；当前返回体仍以替换后的文本为准，
    # 不再对原始查询做重复拼接，避免长度膨胀。
    return " ".join(out.split())
