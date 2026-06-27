#!/usr/bin/env python3
"""Smoke-test SciScope's live agent API and skill contracts.

This script is intentionally black-box: it calls the running FastAPI backend
instead of importing runtime internals. It catches the failures most likely to
hurt demos: sample-corpus status, skill prompts that skip tools, and unbounded
tool loops.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _get_json(url: str, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _skill_prompt(name: str, user_input: str) -> str:
    path = Path(".sciscope") / "skills" / f"{name}.md"
    return path.read_text(encoding="utf-8").replace("{{input}}", user_input)


def _tool_names(result: dict[str, Any]) -> list[str]:
    return [str(item.get("name") or "") for item in result.get("tools_used") or []]


def _check(condition: bool, message: str, failures: list[str]) -> None:
    marker = "ok" if condition else "FAIL"
    print(f"[{marker}] {message}")
    if not condition:
        failures.append(message)


def run(base_url: str, min_papers: int, timeout: int) -> int:
    base = base_url.rstrip("/")
    failures: list[str] = []

    try:
        ingest = _get_json(f"{base}/api/ingest/status", timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[FAIL] backend reachable: {exc}")
        return 2
    papers = int(ingest.get("papers") or 0)
    _check(papers >= min_papers, f"ingest reports DB-sized corpus ({papers} >= {min_papers})", failures)

    cases = [
        {
            "label": "capability boundary",
            "question": "除了科研文献，你还会什么？",
            "want_steps": 0,
            "want_tools": [],
            "max_steps": 0,
        },
        {
            "label": "claim-check skill",
            "question": _skill_prompt("claim-check", "RAG 能降低大语言模型幻觉"),
            "want_tools_prefix": ["verify_claim"],
            "max_steps": 2,
        },
        {
            "label": "trend-analysis skill",
            "question": _skill_prompt("trend-analysis", "retrieval augmented generation"),
            "want_tools_prefix": ["get_trends"],
            "max_steps": 2,
        },
        {
            "label": "paper-recommendation skill",
            "question": _skill_prompt("paper-recommendation", "graph rag"),
            "want_tools_prefix": ["search_literature", "recommend_papers"],
            "max_steps": 2,
        },
    ]

    for case in cases:
        try:
            result = _post_json(f"{base}/api/agent", {"question": case["question"]}, timeout)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            _check(False, f"{case['label']} request succeeds: {exc}", failures)
            continue

        steps = int(result.get("steps") or 0)
        tools = _tool_names(result)
        max_steps = int(case["max_steps"])
        _check(steps <= max_steps, f"{case['label']} stays within tool budget (steps={steps}, max={max_steps})", failures)
        if "want_steps" in case:
            _check(steps == int(case["want_steps"]), f"{case['label']} has expected steps={case['want_steps']}", failures)
        if "want_tools" in case:
            _check(tools == case["want_tools"], f"{case['label']} uses tools {case['want_tools']}", failures)
        if "want_tools_prefix" in case:
            prefix = case["want_tools_prefix"]
            _check(tools[: len(prefix)] == prefix, f"{case['label']} uses tool prefix {prefix} (got {tools})", failures)
        _check(bool(result.get("answer")), f"{case['label']} returns a final answer", failures)

    if failures:
        print("\nAgent smoke failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nAgent smoke passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--min-papers", type=int, default=100000)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    return run(args.base_url, args.min_papers, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
