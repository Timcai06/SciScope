"""Cross-query paper dedup in the tool runner.

Pinned from the 2026-07 experience run: four differently-worded searches in one
turn returned the same paper three times, burning context and reading as fresh
evidence each time. Within a turn, papers already shown are compacted to a note.
"""

from __future__ import annotations

import json

from backend.app.agent import tool_runner as TR


def _paper(pid: str, title: str = "t") -> dict:
    return {"paper_id": pid, "标题": title, "年份": 2024}


def _search_call(query: str) -> dict:
    return {
        "id": f"call-{query}",
        "type": "function",
        "function": {"name": "search_literature", "arguments": json.dumps({"query": query})},
    }


def test_known_paper_ids_reads_flat_and_nested_results():
    executed = {
        "search|a": json.dumps([_paper("W1"), _paper("W2")]),
        "verify|b": json.dumps({"论断": "x", "证据": [_paper("W3")]}),
        "note|c": TR.REPEAT_NOTE,  # non-JSON entries are skipped
    }
    assert TR._known_paper_ids(executed) == {"W1", "W2", "W3"}


def test_dedupe_compacts_repeats_and_keeps_fresh():
    result = json.dumps([_paper("W1"), _paper("W9", "fresh")])
    out = json.loads(TR._dedupe_papers(result, seen={"W1"}))
    assert out[0]["paper_id"] == "W9"
    assert "已省略" in out[-1]["提示"]
    assert len(out) == 2  # one fresh + one note


def test_dedupe_all_repeats_tells_model_to_change_angle():
    result = json.dumps([_paper("W1"), _paper("W2")])
    out = TR._dedupe_papers(result, seen={"W1", "W2"})
    assert "全部与本轮此前结果重复" in out
    assert "换一个明显不同的检索角度" in out


def test_dedupe_leaves_non_list_results_alone():
    assert TR._dedupe_papers("未检索到相关论文。", {"W1"}) == "未检索到相关论文。"
    detail = json.dumps({"paper_id": "W1", "title": "t"})  # get_paper-style dict
    assert TR._dedupe_papers(detail, {"W1"}) == detail


def test_run_tools_dedupes_across_differently_worded_queries(monkeypatch):
    # Two queries, same top paper: the second result must not repeat it in full.
    monkeypatch.setattr(
        TR,
        "execute_tool",
        lambda name, args, on_progress=None: json.dumps(
            [_paper("W1"), _paper("W2" if args["query"] == "第二个说法" else "W1b")]
        ),
    )
    executed: dict[str, str] = {}
    first = TR.run_tools([_search_call("第一个说法")], executed)
    second = TR.run_tools([_search_call("第二个说法")], executed)
    assert len(json.loads(first[0])) == 2  # first query untouched
    out = json.loads(second[0])
    ids = [d.get("paper_id") for d in out if "paper_id" in d]
    assert ids == ["W2"]  # W1 compacted away
    assert "已省略" in out[-1]["提示"]
