"""D05 结构化文献出口数据层。

让 Agent/API 能按 paper ID 返回 D03 的结构化字段，并明确三类边界：

1. **未抽取**：字段 ``status ∈ {not_found, low_confidence}`` → 不输出确定值；
2. **未授权展示**：许可分级（``usage_rights``）不允许展示正文片段时，即使字段已抽取，
   其 ``value`` 也不返回（标记 ``not_authorized_display``）——未知许可一律保守拒绝；
3. **无来源字段不是事实**：只有 ``status=extracted`` 且带 evidence 的字段才作为结果输出。

数据源：D03 输出 ``data/admission/structured/structured.jsonl`` + D01 准入记录
``data/admission/staged.jsonl``（提供 license / usage_rights）。均为文件中间层，
不依赖数据库；索引为空时如实返回“索引未就绪”，不伪装成功。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "structured-export/v1"

DEFAULT_STRUCTURED_PATH = "data/admission/structured/structured.jsonl"
DEFAULT_ADMISSION_PATH = "data/admission/staged.jsonl"

# 允许展示正文片段/证据句的许可分级。
SNIPPET_OR_ABOVE = frozenset({"snippet", "redistributable"})

# D02 的 chunk_uid 由 ``stable_uid`` 生成，是 40 位 SHA-1；未授权出口只接受
# 这个不透明标识。locator 也只输出受控类型，不能把中间层的任意字符串当作审计元数据
# 回显（否则被污染的 locator 本身可成为正文泄露通道）。
_CHUNK_UID_RE = re.compile(r"^[0-9a-f]{40}$")
_LOCATOR_BASES = frozenset({"field_text", "normalized_text", "normalized_page_text"})


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_structured_index(path: str | Path = DEFAULT_STRUCTURED_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    """读 D03 structured.jsonl → {(source, paper_id): record}。"""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for record in _read_jsonl(Path(path)):
        key = (str(record.get("source") or "unknown"), str(record.get("paper_id") or "unknown"))
        index[key] = record
    return index


def load_admission_index(path: str | Path = DEFAULT_ADMISSION_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    """读 D01 staged.jsonl → {(source, paper_id): {license, usage_rights, ...}}。"""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for record in _read_jsonl(Path(path)):
        key = (str(record.get("source") or "unknown"), str(record.get("paper_id") or "unknown"))
        index[key] = {
            "license": record.get("license"),
            "usage_rights": record.get("usage_rights"),
            "source_file_sha256": record.get("source_file_sha256"),
        }
    return index


def _audit_reference(field: dict[str, Any], evidence: dict[str, Any] | None) -> dict[str, Any]:
    """未授权展示时返回的**最小审计引用**：不含正文证据句、不含 span/精确 offset。

    - ``chunk_uid``：可回链 chunk（不含正文内容）；
    - ``locator_type``：粗粒度定位标识（``base`` / ``field`` / ``page``），
      不可复原正文；
    - ``confidence``：置信度。
    """
    locator = (evidence or {}).get("locator") or {}
    base = locator.get("base") if isinstance(locator, dict) else None
    locator_type = base if base in _LOCATOR_BASES else "unknown"
    chunk_uid = (evidence or {}).get("chunk_uid")
    return {
        "chunk_uid": chunk_uid if isinstance(chunk_uid, str) and _CHUNK_UID_RE.fullmatch(chunk_uid) else None,
        "locator_type": locator_type,
        "confidence": field.get("confidence"),
    }


def _has_complete_evidence(evidence: Any) -> bool:
    """判定已抽取字段是否具备可展示的最小事实锚点。

    ``status=extracted`` 不是事实展示授权。授权出口还必须有可回链的 chunk、
    非空证据句和有效字符区间；否则不能把孤立 ``value`` 当作已经被证据支撑的结论。
    """
    if not isinstance(evidence, dict):
        return False
    if not evidence.get("chunk_uid"):
        return False
    if not isinstance(evidence.get("locator"), dict) or not evidence["locator"]:
        return False
    if not isinstance(evidence.get("sentence"), str) or not evidence["sentence"].strip():
        return False
    span = evidence.get("span")
    return (
        isinstance(span, dict)
        and isinstance(span.get("start_char"), int)
        and isinstance(span.get("end_char"), int)
        and span["start_char"] >= 0
        and span["end_char"] > span["start_char"]
    )


def _field_view(field: dict[str, Any], *, display_authorized: bool) -> dict[str, Any]:
    """单字段出口视图：未抽取不输出值；未授权展示不输出值**也不输出正文证据句/候选句**。"""
    view: dict[str, Any] = {
        "field": field.get("field"),
        "status": field.get("status"),
        "confidence": field.get("confidence"),
    }
    if field.get("status") == "extracted":
        if display_authorized:
            evidence = field.get("evidence")
            if _has_complete_evidence(evidence):
                # snippet/redistributable：仅在事实锚点完整时展示正文片段级 value。
                view["value"] = field.get("value")
                view["evidence"] = evidence
            else:
                # 已授权不等于已证实；不输出缺少可回链证据的孤立 value。
                view["value"] = None
                view["display"] = "not_grounded"
                view["reason"] = "extracted_field_missing_valid_evidence"
        else:
            # indexable/unknown：value、evidence.sentence、span 一律不返回，
            # 只留最小审计引用（不把“索引可用”偷换为“正文可展示”）。
            view["value"] = None
            view["display"] = "not_authorized_display"
            view["audit"] = _audit_reference(field, field.get("evidence"))
    else:
        # 未抽取：value 不作为确定事实输出。
        view["value"] = None
        if field.get("reason"):
            view["reason"] = field.get("reason")
        if display_authorized:
            # 已授权（snippet/redistributable）：低置信时附待审候选句。
            if field.get("candidates"):
                view["pending_candidates"] = field.get("candidates")[:5]
        else:
            # 未授权：不得返回任何原文候选句。
            view["display"] = "not_authorized_display"
    return view


def query_structured(
    paper_id: str,
    source: str | None = None,
    *,
    structured_index: dict[tuple[str, str], dict[str, Any]] | None = None,
    admission_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """按 paper ID 查询结构化字段 + 来源 + 置信度 + 许可边界。

    返回单个论文视图；``source=None`` 且多个来源命中时返回 ``matches`` 列表
    （不猜测唯一来源）。
    """
    structured_index = structured_index if structured_index is not None else load_structured_index()
    admission_index = admission_index if admission_index is not None else load_admission_index()

    paper_id = str(paper_id or "").strip()
    if not paper_id:
        return {"schema_version": SCHEMA_VERSION, "paper_id": "", "status": "invalid_request", "reason": "paper_id_empty"}

    keys = (
        [(source, paper_id)]
        if source
        else [key for key in structured_index if key[1] == paper_id]
    )
    matched = [(key, structured_index[key]) for key in keys if key in structured_index]
    if not matched:
        return {
            "schema_version": SCHEMA_VERSION,
            "paper_id": paper_id,
            "source": source,
            "status": "not_found",
            "reason": "no_structured_record",
        }

    if len(matched) > 1:
        return {
            "schema_version": SCHEMA_VERSION,
            "paper_id": paper_id,
            "status": "multiple_sources",
            "matches": [
                query_structured(paper_id, src, structured_index=structured_index, admission_index=admission_index)
                for (src, _), _ in matched
            ],
        }

    (src, _), record = matched[0]
    admission = admission_index.get((src, paper_id)) or {}
    usage_rights = str(admission.get("usage_rights") or "")
    license_value = admission.get("license")

    # 许可边界：仅 snippet/redistributable 允许展示正文片段级结构化值；
    # indexable 只可索引元数据；未知许可保守拒绝展示。
    if usage_rights in SNIPPET_OR_ABOVE:
        authorized, reason = True, "usage_rights_allows_display"
    elif usage_rights == "indexable":
        authorized, reason = False, "indexable_only_metadata_not_display"
    else:
        authorized, reason = False, "usage_rights_unknown_conservative"

    fields = [_field_view(f, display_authorized=authorized) for f in record.get("fields", [])]
    return {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source": src,
        "record_sha256": record.get("record_sha256"),
        "license": license_value,
        "usage_rights": usage_rights or "unknown",
        "display_policy": {"authorized": authorized, "reason": reason},
        "fields": fields,
    }
