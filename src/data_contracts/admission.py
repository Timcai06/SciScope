"""受控摄取数据合同（D01）。

把「新增论文进入 canonical / 运行库之前必须满足的准入字段与校验规则」集中在本模块：

- 字段：稳定 ID、来源、许可、双哈希（原始文件字节哈希 + 记录哈希）、语言、时间、
  可用范围、删除/更正标记；
- 拒绝缺少来源或许可状态的输入，并把拒绝原因写入可查询日志（JSONL）；
- 通过合同的记录写入受控暂存区（默认 ``data/admission/staged.jsonl``），等待 D02
  解析与切片；所有路径可用参数注入，测试使用临时目录。

字段字典见同目录 ``ADMISSION.md``；字段与 D00 数据准入清单 §7「讯飞数据最小元数据」
一一对应。本模块只做准入，不修改既有 ``Paper`` 模型与 ``normalize`` 流程。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

# 默认受控暂存区：对应 D00 清单 §7「讯飞数据只能保存在受控原始区」。
DEFAULT_STAGED_DIR = "data/admission"
STAGED_FILE = "staged.jsonl"
REJECTION_FILE = "rejections.jsonl"

# 三权限分级（D00 清单 §6）。
USAGE_RIGHTS = frozenset({"indexable", "snippet", "redistributable"})

# 可再分发的许可（保守集合：只有明确公有领域许可允许再分发）。
REDISTRIBUTABLE_LICENSES = frozenset({"cc0", "pd", "public-domain"})

# 稳定 ID 允许的字符集：避免路径/注入类字符进入后续文件与数据库键。
_PAPER_ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

# 内容哈希计算时排除的键：两个哈希字段自身与 _sciscope_* 治理元数据。
_EXCLUDED_HASH_KEYS = {"source_file_sha256", "record_sha256"}
_SCOPISCO_PREFIX = "_sciscope_"


@dataclass
class Rejection:
    """单条拒绝原因。``field`` 为出问题的字段，``reason`` 为机器可读说明。"""

    field: str
    reason: str


@dataclass
class IngestDecision:
    """一次摄入决策。``accepted=False`` 时 ``record`` 为 None。"""

    accepted: bool
    record: dict[str, Any] | None
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return [f"{r.field}: {r.reason}" for r in self.rejections]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _record_summary(record: dict[str, Any]) -> dict[str, str]:
    """拒绝日志里只保留少量标识字段，避免把原文大段内容写进日志。"""
    summary: dict[str, str] = {}
    for key in ("paper_id", "source", "license", "language", "year"):
        if key in record:
            summary[key] = _clean(record[key])
    return summary


def compute_record_hash(record: dict[str, Any]) -> str:
    """对规范化记录内容计算 sha256（排除两个哈希字段自身与 ``_sciscope_*`` 元数据）。

    这是「记录哈希」``record_sha256`` 的对照值，**不是**原始论文/PDF 文件的字节哈希：
    原始交付文件的字节哈希由交付方以 ``source_file_sha256`` 提供，本模块只校验其格式，
    内容一致性留给 D02 摄取时回链核验（真实讯飞数据至少要能回链到前者）。
    """
    payload = {
        key: value
        for key, value in record.items()
        if key not in _EXCLUDED_HASH_KEYS and not key.startswith(_SCOPISCO_PREFIX)
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_ingest_record(record: dict[str, Any]) -> IngestDecision:
    """校验一条新增论文记录是否满足受控摄取合同。

    拒绝规则（顺序即返回顺序）：
    1. ``paper_id`` 缺失/为空/含非法字符；
    2. ``source`` 缺失或为空（缺来源样例）；
    3. ``license`` 缺失、为空或为 ``unknown``（许可未知样例）；
    4. ``source_file_sha256`` 缺失或非 64 位 hex（原始交付文件字节哈希，仅格式校验）；
    5. ``record_sha256`` 缺失、非 64 位 hex、或与规范化记录哈希不一致（哈希不符样例）；
    6. ``language`` 缺失或为空；
    7. ``year`` 缺失或不可解析为整数；
    8. ``usage_rights`` 缺失或不在三权限集合内；
    9. ``usage_rights=redistributable`` 但 ``license`` 不在可再分发许可集合；
    10. ``retracted`` 存在但不是布尔值；
    11. ``correction`` 存在但不是字符串。
    """
    rejections: list[Rejection] = []

    paper_id = _clean(record.get("paper_id"))
    if not paper_id:
        rejections.append(Rejection("paper_id", "missing_or_empty"))
    elif not _PAPER_ID_RE.match(paper_id):
        rejections.append(Rejection("paper_id", "illegal_characters"))

    source = _clean(record.get("source"))
    if not source:
        rejections.append(Rejection("source", "missing_or_empty"))

    license_value = _clean(record.get("license"))
    if not license_value:
        rejections.append(Rejection("license", "missing_or_empty"))
    elif license_value.lower() in {"unknown", "n/a", "na"}:
        rejections.append(Rejection("license", "unknown_license"))

    source_file_sha256 = _clean(record.get("source_file_sha256"))
    if not source_file_sha256:
        rejections.append(Rejection("source_file_sha256", "missing_or_empty"))
    elif not _SHA256_HEX_RE.match(source_file_sha256):
        rejections.append(Rejection("source_file_sha256", "not_sha256_hex"))

    record_sha256 = _clean(record.get("record_sha256"))
    if not record_sha256:
        rejections.append(Rejection("record_sha256", "missing_or_empty"))
    elif not _SHA256_HEX_RE.match(record_sha256):
        rejections.append(Rejection("record_sha256", "not_sha256_hex"))
    elif record_sha256 != compute_record_hash(record):
        rejections.append(Rejection("record_sha256", "hash_mismatch"))

    language = _clean(record.get("language"))
    if not language:
        rejections.append(Rejection("language", "missing_or_empty"))

    year = record.get("year")
    try:
        int(year)  # 接受 int 或数字字符串
    except (TypeError, ValueError):
        rejections.append(Rejection("year", "not_an_integer"))

    usage_rights = _clean(record.get("usage_rights"))
    if not usage_rights:
        rejections.append(Rejection("usage_rights", "missing_or_empty"))
    elif usage_rights not in USAGE_RIGHTS:
        rejections.append(Rejection("usage_rights", f"invalid:{usage_rights}"))
    elif usage_rights == "redistributable" and license_value.lower() not in REDISTRIBUTABLE_LICENSES:
        rejections.append(Rejection("usage_rights", "license_not_redistributable"))

    if "retracted" in record and not isinstance(record["retracted"], bool):
        rejections.append(Rejection("retracted", "not_boolean"))
    if "correction" in record and not isinstance(record["correction"], str):
        rejections.append(Rejection("correction", "not_string"))

    if rejections:
        return IngestDecision(accepted=False, record=None, rejections=rejections)

    admitted: dict[str, Any] = dict(record)
    admitted["_sciscope_admission_schema"] = "ingest-contract/v1"
    admitted["_sciscope_admitted_at"] = _utc_now()
    return IngestDecision(accepted=True, record=admitted, rejections=[])


def _append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def ingest_record(
    record: dict[str, Any],
    *,
    staged_dir: str | Path = DEFAULT_STAGED_DIR,
    reject_log_dir: str | Path | None = None,
) -> IngestDecision:
    """校验并（通过时）导入一条记录到受控暂存区。

    - 通过：写入 ``<staged_dir>/staged.jsonl``（原子追加），返回带 ``_sciscope_*``
      元数据的记录；
    - 拒绝：写入 ``<reject_log_dir or staged_dir>/rejections.jsonl``，保留原因与
      时间戳，返回拒绝列表。

    默认目录 ``data/admission/`` 即 D00 清单 §7 的「受控原始区」；测试用
    ``staged_dir``/``reject_log_dir`` 注入临时目录。
    """
    decision = validate_ingest_record(record)
    log_dir = Path(reject_log_dir) if reject_log_dir is not None else Path(staged_dir)
    if decision.accepted:
        assert decision.record is not None
        _append_jsonl(Path(staged_dir) / STAGED_FILE, [decision.record])
    else:
        log_entry = {
            "ts": _utc_now(),
            "record": _record_summary(record),
            "rejections": [{"field": r.field, "reason": r.reason} for r in decision.rejections],
        }
        _append_jsonl(log_dir / REJECTION_FILE, [log_entry])
    return decision
