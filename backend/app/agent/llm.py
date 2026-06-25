"""LLM transport and shared prompt utilities for SciScope agent runtimes."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Iterator


LLM_BASE = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")

SYSTEM_PROMPT = (
    "你是 SciScope 科研文献智能体,可访问一个 16 万篇科技文献的知识库。"
    "你拥有以下工具:search_literature(检索论文)、get_trends(研究趋势)、"
    "recommend_papers(相似论文推荐,需 paper_id)、get_paper(论文详情)、"
    "query_knowledge_graph(知识图谱/研究社区)、verify_claim(用语义接地度核查论断是否有文献支持)。"
    "工作方式:① 对复杂问题先规划需要哪些检索步骤,再依次调用工具(可多步);"
    "recommend_papers/get_paper/compare_papers 需要真实 paper_id——必须先用 search_literature 拿到,"
    "严禁编造 paper_id;② 凡涉及文献事实的问题,必须先调用工具检索证据,不能凭记忆直接回答;"
    "若同一工具同参数已调用过,不要重复调用,改用不同参数或据已有结果作答;"
    "③ 拿到工具结果后用中文综合归纳作答,只依据工具返回的真实数据,不编造,证据不足时如实说明。"
    "注意:检索结果里的「摘要片段」是论文摘要节选,「作者」才是作者。"
    "④ 用结构化 Markdown 作答,层次清晰:先一句话概述结论;再用有序列表分点,"
    "每点以 **加粗论文标题**(年份)开头并简述其贡献;需要时用 `##` 小标题分组(如「代表工作」「研究趋势」);"
    "最后用一句 `> ` 引用块给出小结或趋势判断。避免大段连续文字。"
)


def detect_model() -> str | None:
    try:
        with urllib.request.urlopen(LLM_BASE.rstrip("/") + "/models", timeout=5) as resp:
            return json.loads(resp.read().decode())["data"][0]["id"]
    except Exception:
        return None


def stream_chat(messages: list[dict], model: str, tools: list | None) -> Iterator[tuple[str, Any]]:
    """Stream a chat completion and return ``(full_text, tool_calls)``."""
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True, "temperature": 0.1, "max_tokens": 700}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        LLM_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    full_text = ""
    acc: dict[int, dict[str, Any]] = {}
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                full_text += delta["content"]
                yield ("text", delta["content"])
            for tool_call in delta.get("tool_calls") or []:
                idx = tool_call.get("index", 0)
                slot = acc.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                if tool_call.get("id"):
                    slot["id"] = tool_call["id"]
                fn = tool_call.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    tool_calls = [
        {"id": slot["id"] or slot["name"], "type": "function", "function": {"name": slot["name"], "arguments": slot["arguments"]}}
        for slot in (acc[index] for index in sorted(acc))
        if slot["name"]
    ]
    return full_text, tool_calls


def drain(gen: Iterator[tuple[str, Any]], forward) -> tuple[str, list[dict]]:
    """Forward streamed text events and return a generator's final value."""
    while True:
        try:
            kind, payload = next(gen)
        except StopIteration as stop:
            return stop.value
        forward(kind, payload)


def complete(messages: list[dict], model: str) -> str:
    text, _ = drain(stream_chat(messages, model, None), lambda kind, payload: None)
    return text


def compact(messages: list[dict], budget_chars: int = 20000) -> None:
    """Trim older large tool results while preserving recent conversation shape."""
    total = sum(len(str(message.get("content") or "")) for message in messages)
    if total <= budget_chars:
        return
    for message in messages[1:-4]:
        if message.get("role") == "tool" and len(str(message.get("content") or "")) > 400:
            message["content"] = str(message["content"])[:400] + " …(结果已压缩)"
