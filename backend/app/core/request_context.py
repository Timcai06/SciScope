from __future__ import annotations

import contextvars
import uuid

from fastapi import Request

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
SESSION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def request_id() -> str:
    current = REQUEST_ID.get()
    if current:
        return current
    generated = f"req-{uuid.uuid4().hex[:12]}"
    REQUEST_ID.set(generated)
    return generated


def session_id() -> str:
    return SESSION_ID.get()


def bind_request_context(request: Request) -> str:
    rid = request.headers.get("x-request-id", "").strip() or f"req-{uuid.uuid4().hex[:12]}"
    REQUEST_ID.set(rid)
    sid = request.headers.get("x-sciscope-session", "").strip()
    if sid:
        SESSION_ID.set(sid)
    return rid
