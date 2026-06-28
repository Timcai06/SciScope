"""LLM transport for SciScope agent runtimes (chat streaming, completion, model
detection) plus a thin compaction shim.

System-prompt assembly lives in :mod:`backend.app.agent.prompts`; it is re-exported
here so existing callers (``from backend.app.agent.llm import build_system_prompt``)
keep working while each module has a single job.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Iterator

from backend.app.core.config import get_settings

# Prompt assembly moved out; keep the import surface stable for callers/tests.
from backend.app.agent.prompts import SYSTEM_PROMPT, build_system_prompt  # noqa: F401


def _llm_target() -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) for the generation backend.

    The model layer is pluggable: when ``SCISCOPE_LLM_PROVIDER=deepseek`` and a
    key is set, the agent generates via DeepSeek (OpenAI-compatible cloud) for far
    stronger output than the local 7B; otherwise it uses the local
    OpenAI-compatible endpoint (offline / air-gapped use). Both speak the same
    protocol — only the base URL and auth header differ.
    """
    s = get_settings()
    if s.llm_provider == "deepseek" and s.deepseek_api_key:
        return s.deepseek_base_url.rstrip("/"), s.deepseek_api_key, s.deepseek_model
    base = (s.local_llm_base_url or "http://127.0.0.1:8001/v1").rstrip("/")
    return base, (s.local_llm_api_key or ""), (s.local_llm_model or "")


def _is_cloud_provider() -> bool:
    s = get_settings()
    return s.llm_provider == "deepseek" and bool(s.deepseek_api_key)


def detect_model() -> str | None:
    base, _key, model = _llm_target()
    if _is_cloud_provider():
        # DeepSeek is always reachable; trust the configured model (no probe).
        return model or "deepseek-chat"
    try:
        with urllib.request.urlopen(base + "/models", timeout=5) as resp:
            return json.loads(resp.read().decode())["data"][0]["id"]
    except Exception:
        return None


def stream_chat(messages: list[dict], model: str, tools: list | None) -> Iterator[tuple[str, Any]]:
    """Stream a chat completion and return ``(full_text, tool_calls)``."""
    base, key, _model = _llm_target()
    # Cloud models can write fuller answers; keep the local 7B lean for latency.
    max_tokens = 1500 if _is_cloud_provider() else 700
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True, "temperature": 0.1, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers=headers,
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


def compact(messages: list[dict], budget_chars: int = 20000):
    """Cheap in-place context compaction (microcompact) — see compaction service.

    Backed by :mod:`backend.app.agent.compaction`: keeps the most recent tool
    results and clears older large ones. ``budget_chars`` is converted to a token
    budget (~4 chars/token) for backward compatibility. Returns the
    :class:`CompactionResult` so callers can surface telemetry (older callers that
    ignore the return value are unaffected).
    """
    from backend.app.agent.compaction import compact as _compact

    return _compact(messages, token_budget=max(budget_chars // 4, 1))
