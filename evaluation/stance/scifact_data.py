"""SciFact 锚点数据准入 loader/validator（E02a）。

从 SciFact 官方发布源（AI2 S3，allenai/scifact script/download-data.sh 指向）
下载的数据做准入与完整性校验。本模块只做**数据准入**：

- 缺文件、SHA256 不符、schema 不符一律 fail-closed（抛异常）；
- 输出样本数、标签分布、缺失率、证据引用可解析率等统计；
- 不训练模型、不产生任何 benchmark 分数——分数输出由
  ``evaluation/scifact_eval.py`` 的显式评分路径负责，且默认 dry-run。

数据格式（官方 doc/data.md）：
- claims_*.jsonl: {id:int, claim:str, evidence:{doc_id_str:[{label, sentences}]},
  cited_doc_ids:int[]}；test 集官方无 evidence（无标注）。
- corpus.jsonl: {doc_id:int, title:str, abstract:str[], structured:bool}。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 官方发布源（allenai/scifact script/download-data.sh 指向的唯一上游）。
UPSTREAM_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
# GitHub 仓库代码版本（数据 release 为浮动标签，无固定 commit；记录下载时 master tree sha 作参考）。
UPSTREAM_REPO = "https://github.com/allenai/scifact"
UPSTREAM_TREE_SHA = "68b98a56d93e0f9da0d2aab4e6c3294699a0f72e"  # 2026-08-08 查询

# 官方许可（LICENSE.md）：claims 为 CC BY 4.0；corpus 摘要为 ODC-By 1.0（S2ORC）。
CLAIMS_LICENSE = "CC BY 4.0"
CORPUS_LICENSE = "ODC-By 1.0"

# 文件字节 SHA256（2026-08-08 从官方 S3 下载后实测，见 E02a 报告）。
RAW_SHA256 = {
    "claims_train.jsonl": "f4c8fa82d8bd0653a9cc8d61a6ea48c25eacea64e90af5dbf390ebb1b74372f0",
    "claims_dev.jsonl": "86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217",
    "claims_test.jsonl": "558930d75215c73f84a28fe538307d6d397c9de1ec7239514cf45f80d75d2ca3",
    "corpus.jsonl": "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62",
}

REQUIRED_CLAIM_FIELDS = {"id", "claim", "evidence"}
REQUIRED_CORPUS_FIELDS = {"doc_id", "title", "abstract", "structured"}
LABELS = {"SUPPORT", "CONTRADICT"}  # 官方 rationale 标签；NEUTRAL 为"无证据 claim"的隐式类别
EXPECTED_SHA = RAW_SHA256  # 兼容别名


class SciFactDataError(RuntimeError):
    """数据准入失败：缺文件 / 哈希不符 / schema 不符。fail-closed。"""


@dataclass
class SciFactStats:
    """数据完整性统计（不包含任何模型分数）。"""

    split: str
    claims: int
    claims_with_evidence: int
    rationale_count: int
    label_distribution: dict[str, int]
    cited_doc_refs: int
    cited_doc_resolvable: int
    rationale_sentence_refs: int
    rationale_sentence_valid: int
    corpus_docs: int

    @property
    def evidence_missing_rate(self) -> float:
        return round(1.0 - self.claims_with_evidence / max(1, self.claims), 4)

    @property
    def doc_ref_resolvable_rate(self) -> float:
        return round(self.cited_doc_resolvable / max(1, self.cited_doc_refs), 4)

    @property
    def sentence_ref_valid_rate(self) -> float:
        return round(self.rationale_sentence_valid / max(1, self.rationale_sentence_refs), 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "split": self.split,
            "claims": self.claims,
            "claims_with_evidence": self.claims_with_evidence,
            "evidence_missing_rate": self.evidence_missing_rate,
            "rationale_count": self.rationale_count,
            "label_distribution": self.label_distribution,
            "cited_doc_refs": self.cited_doc_refs,
            "cited_doc_resolvable": self.cited_doc_resolvable,
            "doc_ref_resolvable_rate": self.doc_ref_resolvable_rate,
            "rationale_sentence_refs": self.rationale_sentence_refs,
            "rationale_sentence_valid": self.rationale_sentence_valid,
            "sentence_ref_valid_rate": self.sentence_ref_valid_rate,
            "corpus_docs": self.corpus_docs,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SciFactDataError(f"{path}:{number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise SciFactDataError(f"{path}:{number}: expected object")
        rows.append(row)
    return rows


def load_corpus(corpus_path: Path) -> dict[int, dict[str, Any]]:
    """Load corpus keyed by int doc_id; fail-closed on schema violation."""
    corpus: dict[int, dict[str, Any]] = {}
    for number, row in enumerate(_read_jsonl(corpus_path), start=1):
        missing = REQUIRED_CORPUS_FIELDS - set(row)
        if missing:
            raise SciFactDataError(f"{corpus_path}:{number}: missing corpus fields {sorted(missing)}")
        try:
            doc_id = int(row["doc_id"])
        except (TypeError, ValueError) as exc:
            raise SciFactDataError(f"{corpus_path}:{number}: non-integer doc_id") from exc
        if not isinstance(row["abstract"], list) or not all(isinstance(s, str) for s in row["abstract"]):
            raise SciFactDataError(f"{corpus_path}:{number}: abstract must be a list of strings")
        corpus[doc_id] = row
    return corpus


def validate_claims(rows: list[dict[str, Any]], corpus: dict[int, dict[str, Any]], split: str, path: Path) -> SciFactStats:
    """Validate claim schema, labels, and evidence references; return stats.

    Fail-closed on schema violations and on unresolvable evidence references.
    NEUTRAL is the implicit category for claims without evidence (official data
    has no explicit NEUTRAL rationale label).
    """
    label_counts: Counter[str] = Counter()
    rationale_count = 0
    cited_refs = 0
    cited_resolvable = 0
    sentence_refs = 0
    sentence_valid = 0
    with_evidence = 0

    # 官方 schema：test 集无标注（无 evidence），train/dev 必须有 evidence 字段。
    required = REQUIRED_CLAIM_FIELDS if split != "test" else REQUIRED_CLAIM_FIELDS - {"evidence"}
    for number, row in enumerate(rows, start=1):
        missing = required - set(row)
        if missing:
            raise SciFactDataError(f"{path}:{number}: missing claim fields {sorted(missing)}")
        if not isinstance(row.get("claim"), str) or not row["claim"].strip():
            raise SciFactDataError(f"{path}:{number}: claim text missing/blank")
        evidence = row.get("evidence")
        if evidence is None:
            evidence = {}  # 官方 test 集无 evidence 字段，等价于无标注
        if not isinstance(evidence, dict):
            raise SciFactDataError(f"{path}:{number}: evidence must be an object")

        if evidence:
            with_evidence += 1
            for doc_key, rationales in evidence.items():
                cited_refs += 1
                try:
                    doc_id = int(doc_key)
                except (TypeError, ValueError) as exc:
                    raise SciFactDataError(f"{path}:{number}: non-integer evidence doc key {doc_key!r}") from exc
                if doc_id not in corpus:
                    raise SciFactDataError(f"{path}:{number}: evidence doc {doc_id} missing from corpus")
                cited_resolvable += 1
                if not isinstance(rationales, list):
                    raise SciFactDataError(f"{path}:{number}: evidence rationales must be a list")
                for rationale in rationales:
                    rationale_count += 1
                    label = str(rationale.get("label") or "").upper()
                    if label not in LABELS:
                        raise SciFactDataError(f"{path}:{number}: invalid rationale label {label!r}")
                    label_counts[label] += 1
                    sentences = rationale.get("sentences")
                    if not isinstance(sentences, list) or not all(isinstance(s, int) for s in sentences):
                        raise SciFactDataError(f"{path}:{number}: sentences must be int list")
                    abstract_len = len(corpus[doc_id]["abstract"])
                    for sent in sentences:
                        sentence_refs += 1
                        if 0 <= sent < abstract_len:
                            sentence_valid += 1
        else:
            label_counts["NEUTRAL"] += 1

    if sentence_refs != sentence_valid:
        raise SciFactDataError(f"{path}: {sentence_refs - sentence_valid} sentence refs out of abstract bounds")
    if split == "test" and with_evidence:
        # 官方 test 集无标注；出现证据说明数据异常（fail-closed）。
        raise SciFactDataError(f"{path}: test split must have no evidence annotations")
    return SciFactStats(
        split=split,
        claims=len(rows),
        claims_with_evidence=with_evidence,
        rationale_count=rationale_count,
        label_distribution=dict(label_counts),
        cited_doc_refs=cited_refs,
        cited_doc_resolvable=cited_resolvable,
        rationale_sentence_refs=sentence_refs,
        rationale_sentence_valid=sentence_valid,
        corpus_docs=len(corpus),
    )


def verify_split(raw_dir: Path, split: str, expected_sha: dict[str, str] | None = None) -> SciFactStats:
    """Full admission check for one claims split + corpus.

    Fail-closed: missing file, SHA mismatch, schema violation, or unresolvable
    reference all raise ``SciFactDataError``.  ``expected_sha`` overrides the
    built-in official hashes (used by tests with synthetic fixtures).
    """
    expected_sha = expected_sha or RAW_SHA256
    if split not in {"train", "dev", "test"}:
        raise SciFactDataError(f"unknown split {split!r}")
    corpus_path = raw_dir / "corpus.jsonl"
    claims_path = raw_dir / f"claims_{split}.jsonl"
    for path in (corpus_path, claims_path):
        if not path.exists():
            raise SciFactDataError(f"missing file: {path}")
    for path in (corpus_path, claims_path):
        actual = _sha256(path)
        want = expected_sha[path.name]
        if actual != want:
            raise SciFactDataError(f"SHA256 mismatch for {path.name}: got {actual}, want {want}")
    corpus = load_corpus(corpus_path)
    claims = _read_jsonl(claims_path)
    return validate_claims(claims, corpus, split, claims_path)
