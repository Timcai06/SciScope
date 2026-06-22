#!/usr/bin/env python3
"""Interactive terminal chat with the SciScope research agent.

Talks to the corpus directly (no web server needed): hybrid retrieval over
PostgreSQL + pgvector, then a grounded answer from the local LLM running on
:8001. The local model name is auto-detected from the vLLM /v1/models endpoint,
so it works whether you serve the 0.5B or the 7B model.

Run:
    /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python scripts/chat_cli.py
or:
    make chat
"""

from __future__ import annotations

import os
import sys
import urllib.request
import json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

DSN = os.getenv("SCISCOPE_DB_DSN", "postgresql://tim@localhost:5432/sciscope")
LLM_BASE = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
EMBEDDER = os.getenv("SCISCOPE_EMBEDDER_PATH", os.path.join(REPO, "models/embedder_local/multilingual-e5-base"))


def detect_local_model(base_url: str) -> str | None:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["data"][0]["id"]
    except Exception:
        return None


def main() -> None:
    model = detect_local_model(LLM_BASE)
    # Configure the backend via env before importing it.
    os.environ["SCISCOPE_DB_DSN"] = DSN
    os.environ["SCISCOPE_EMBEDDER_PATH"] = EMBEDDER
    if model:
        os.environ["SCISCOPE_USE_MOCK_LLM"] = "false"
        os.environ["SCISCOPE_LLM_PROVIDER"] = "vllm"
        os.environ["LOCAL_LLM_BASE_URL"] = LLM_BASE
        os.environ["LOCAL_LLM_MODEL"] = model
    else:
        os.environ.setdefault("SCISCOPE_USE_MOCK_LLM", "true")

    from backend.app.services.corpus_service import get_corpus
    from backend.app.services.evidence_chat import answer_question

    mode = f"local LLM ({model})" if model else "MOCK (no local LLM on :8001)"
    print(f"SciScope terminal chat — generation: {mode}")
    print("多轮对话已开启(支持追问)。Type a question (中文/English). 空行或 Ctrl-C 退出。\n")

    corpus = []  # only used by the in-memory fallback when DB is unavailable
    history: list[dict] = []  # multi-turn conversation memory

    while True:
        try:
            question = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not question:
            break

        try:
            response = answer_question(question, corpus, history=history)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}\n")
            continue

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response.answer})
        history[:] = history[-8:]  # keep last 4 turns

        print(f"\n[confidence: {response.confidence}]")
        print(f"AI> {response.answer}\n")
        if response.evidence:
            print("证据 (evidence):")
            for i, ev in enumerate(response.evidence, 1):
                print(f"  [{i}] ({ev.year or '—'}) {ev.title}")
            print()


if __name__ == "__main__":
    main()
