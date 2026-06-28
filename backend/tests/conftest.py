"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_agent_memory(tmp_path, monkeypatch):
    """Point session memory at a per-test tmp dir so tests never write to the repo."""
    monkeypatch.setenv("SCISCOPE_AGENT_MEMORY_DIR", str(tmp_path / "agent_memory"))
