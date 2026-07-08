"""Stance persistence service: row shaping, upsert keys, fail-open guarantees."""

from __future__ import annotations

import pytest

from backend.app.services import stance_store


class _FakeCursor:
    def __init__(self, store: "_FakeConn") -> None:
        self._store = store

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        self._store.executed.append((sql, rows))

    def execute(self, sql: str, params: tuple) -> None:
        self._store.executed.append((sql, params))

    def fetchall(self) -> list[tuple]:
        return self._store.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeConn:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self.executed: list[tuple] = []
        self.rows = rows or []
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


EVIDENCE = [
    {"paper_id": "W1", "标题": "Coffee study", "年份": 2023, "立场": "SUPPORT", "接地相似度": 0.9},
    {"paper_id": "W2", "标题": "Contra study", "年份": 2024, "立场": "CONTRADICT", "接地相似度": 0.85},
    {"paper_id": "W3", "标题": "No label", "年份": 2022, "接地相似度": 0.8},  # skipped: no stance
    {"标题": "No id", "立场": "SUPPORT"},  # skipped: no paper_id
]


def test_normalize_claim_folds_case_space_punct():
    assert stance_store.normalize_claim("咖啡能降低心脏病风险!") == stance_store.normalize_claim("  咖啡能降低心脏病风险  ")
    assert stance_store.normalize_claim("LLMs Increase Risk") == stance_store.normalize_claim("llms increase risk")


def test_record_stances_writes_labeled_rows_only(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConn()
    monkeypatch.setattr(stance_store, "_connect", lambda: conn)
    written = stance_store.record_stances("咖啡能降低心脏病风险", "存在争议", EVIDENCE)
    assert written == 2
    _sql, rows = conn.executed[0]
    assert [(r[2], r[5]) for r in rows] == [("W1", "SUPPORT"), ("W2", "CONTRADICT")]
    assert all(r[1] == stance_store.normalize_claim("咖啡能降低心脏病风险") for r in rows)
    assert all(r[7] == "存在争议" for r in rows)
    assert conn.closed


def test_record_stances_noop_without_dsn(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(stance_store, "_connect", lambda: None)
    assert stance_store.record_stances("论断", "强支持", EVIDENCE) == 0


def test_record_stances_swallows_db_errors(monkeypatch: pytest.MonkeyPatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(stance_store, "_connect", _boom)
    # Fail-open: persistence failure must not raise into the answer path.
    assert stance_store.record_stances("论断", "强支持", EVIDENCE) == 0


def test_record_stances_skips_when_nothing_labeled(monkeypatch: pytest.MonkeyPatch):
    called = []
    monkeypatch.setattr(stance_store, "_connect", lambda: called.append(1))
    assert stance_store.record_stances("论断", "证据不足", [{"paper_id": "W3"}]) == 0
    assert not called  # doesn't even open a connection


def test_disputed_claims_maps_view_rows(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConn(rows=[("咖啡能降低心脏病风险", 3, 2, 5, "2026-07-08")])
    monkeypatch.setattr(stance_store, "_connect", lambda: conn)
    out = stance_store.disputed_claims(limit=10)
    assert out == [{
        "claim": "咖啡能降低心脏病风险",
        "support_count": 3,
        "contradict_count": 2,
        "paper_count": 5,
        "last_seen": "2026-07-08",
    }]


def test_disputed_claims_fail_open(monkeypatch: pytest.MonkeyPatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(stance_store, "_connect", _boom)
    assert stance_store.disputed_claims() == []
