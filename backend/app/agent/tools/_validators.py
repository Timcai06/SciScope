"""Shared input validators for paper-id tools.

Several tools take a ``paper_id`` the model is supposed to have *retrieved* via
``search_literature``. These validators catch the real failure modes — a topic
phrase passed as an id, or a fabricated zero-padded placeholder — before the DB
sees them, and return a recovery message telling the model how to proceed.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_IDS = {"string", "paper_id", "id", "example", "xxx", "n/a", "none", "null", "0"}
_FABRICATED_NUM = re.compile(r"^0+1?$")  # "0000001" etc. — the model's fabricated-id pattern


def validate_paper_id(value: Any, field: str = "paper_id") -> str | None:
    """Reject ids the model fabricated instead of retrieving. None means OK.

    Catches the real failure modes (a topic phrase passed as an id, or a
    zero-padded placeholder) and tells the model how to recover. It does NOT
    require a specific id scheme — real OpenAlex/DOI ids pass through.
    """
    pid = str(value or "").strip()
    if not pid:
        return f"{field} 为空——请先用 search_literature 检索,用返回的真实 paper_id 再调用。"
    if " " in pid or len(pid) > 80:
        return f"{field}={pid!r} 不像论文 ID(疑似把主题/短语当成 ID)。请先用 search_literature 拿到真实 paper_id。"
    if pid.lower() in _PLACEHOLDER_IDS or _FABRICATED_NUM.match(pid):
        return f"{field}={pid!r} 像是编造的占位 ID。请先用 search_literature 拿到真实 paper_id。"
    return None


def v_paper_id(args: dict[str, Any]) -> str | None:
    return validate_paper_id(args.get("paper_id"))


def v_compare(args: dict[str, Any]) -> str | None:
    return validate_paper_id(args.get("paper_id_a"), "paper_id_a") or validate_paper_id(
        args.get("paper_id_b"), "paper_id_b"
    )


def v_export(args: dict[str, Any]) -> str | None:
    ids = args.get("paper_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    cleaned = [str(x).strip() for x in ids if str(x).strip()]
    if not cleaned:
        return "paper_ids 为空——请先用 search_literature 拿到真实 paper_id。"
    for x in cleaned:
        denial = validate_paper_id(x, "paper_ids 元素")
        if denial:
            return denial
    return None
