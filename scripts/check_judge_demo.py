"""Validate the frozen judge-demo evidence without starting heavy workloads.

This preflight verifies checked-in evidence and reports human-owned gates
separately. It does not call a model, rebuild embeddings, or manufacture a
reviewer/video PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Check:
    check_id: str
    status: str
    detail: str
    evidence: str


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def contains(path: Path, *needles: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(needle in text for needle in needles)


def verify_sha256(root: Path, manifest: Path) -> tuple[bool, str]:
    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        path = root / relative
        if not path.is_file():
            return False, f"missing {relative}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            return False, f"hash mismatch {relative}"
        checked += 1
    return True, f"{checked} files verified"


def build_checks(root: Path) -> list[Check]:
    evidence = root / "output/evidence"
    t04 = evidence / "t04"
    summary_path = t04 / "online/summary.json"
    manifest_path = t04 / "runtime/manifest.md"
    checks: list[Check] = []

    required = [
        summary_path,
        manifest_path,
        t04 / "tui/isolated-online-verify-pane.txt",
        t04 / "tui/retry-online-verify-pane.txt",
        t04 / "offline/demo-pane.txt",
        t04 / "offline/failure-pane.txt",
        evidence / "e04/opencode_run_e04.jsonl",
        root / "output/pdf/sciscope_project_report/sciscope_project_report.pdf",
        root / "output/pdf/sciscope_data_report/sciscope_data_report.pdf",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    checks.append(
        Check(
            "required-assets",
            "PASS" if not missing else "FAIL",
            "all required assets exist" if not missing else f"missing: {', '.join(missing)}",
            "output/evidence/t04, output/evidence/e04, output/pdf",
        )
    )

    if summary_path.is_file():
        summary = read_json(summary_path)
        runs = summary.get("runs")
        valid_runs = isinstance(runs, list) and len(runs) == 3 and all(
            isinstance(run, dict)
            and run.get("http_status") == 200
            and run.get("done") is True
            and run.get("has_error") is False
            and run.get("citation_compliance") == "ok"
            for run in runs
        )
        checks.append(
            Check(
                "three-online-runs",
                "PASS" if valid_runs else "FAIL",
                "3 runs: HTTP 200, DONE, no error, citations ok" if valid_runs else "online run contract failed",
                "output/evidence/t04/online/summary.json",
            )
        )
        readiness = summary.get("readyz", {}).get("checks", {})
        ready = all(readiness.get(name, {}).get("status") == "configured" for name in ("db", "retrieval", "model"))
        checks.append(
            Check(
                "recorded-readiness",
                "PASS" if ready else "FAIL",
                "DB, retrieval/pgvector and model configured" if ready else "recorded readiness incomplete",
                "output/evidence/t04/online/readyz.json",
            )
        )

    manifest_ok = contains(
        manifest_path,
        "papers|159164",
        "paper_chunks|367861",
        "paper_embeddings|159164",
        "chunk_embeddings|367861",
        "NVIDIA GeForce RTX 2080 Ti",
    )
    checks.append(
        Check(
            "full-corpus-hardware",
            "PASS" if manifest_ok else "FAIL",
            "full corpus, complete vectors and RTX 2080 Ti recorded" if manifest_ok else "manifest values incomplete",
            "output/evidence/t04/runtime/manifest.md",
        )
    )

    first_closed = contains(
        t04 / "tui/isolated-online-verify-pane.txt",
        "generative_non_evidentiary",
        "missing_required_citations",
    )
    retry_ok = contains(t04 / "tui/retry-online-verify-pane.txt", "citations ok", "审计链")
    checks.append(
        Check(
            "tui-fail-closed-and-retry",
            "PASS" if first_closed and retry_ok else "FAIL",
            "first citation failure retained; recorded retry passed" if first_closed and retry_ok else "TUI evidence incomplete",
            "output/evidence/t04/tui",
        )
    )

    offline_ok = contains(t04 / "offline/demo-pane.txt", "论断核查", "会话已保存")
    failure_ok = contains(t04 / "offline/failure-pane.txt", "后端未连接", "/retry", "/doctor")
    checks.append(
        Check(
            "offline-and-failure-fallback",
            "PASS" if offline_ok and failure_ok else "FAIL",
            "offline fixture and explicit blocked recovery captured" if offline_ok and failure_ok else "fallback evidence incomplete",
            "output/evidence/t04/offline",
        )
    )

    opencode = evidence / "e04/opencode_run_e04.jsonl"
    opencode_ok = contains(opencode, '"tool":"sciscope_verify_claim"', '"persist":true', '"tool":"read_mcp_resource"', "sciscope://disputes/recent")
    checks.append(
        Check(
            "opencode-mcp-order",
            "PASS" if opencode_ok else "FAIL",
            "verify_claim(persist=true) precedes disputes resource read; fixture boundary applies" if opencode_ok else "OpenCode sequence missing",
            "output/evidence/e04/opencode_run_e04.jsonl",
        )
    )

    sha_manifest = t04 / "SHA256SUMS"
    sha_ok, sha_detail = verify_sha256(root, sha_manifest) if sha_manifest.is_file() else (False, "SHA256SUMS missing")
    checks.append(Check("evidence-integrity", "PASS" if sha_ok else "FAIL", sha_detail, "output/evidence/t04/SHA256SUMS"))

    checks.extend(
        [
            Check("technical-video", "PENDING", "record 60-second submission video and 6-8 minute technical video", "human-owned recording"),
            Check("nontechnical-review", "PENDING", "a non-project reviewer must complete the timed acceptance form", "human-owned acceptance"),
        ]
    )
    return checks


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# E07 judge-demo preflight",
        "",
        f"- generated: `{payload['generated_at']}`",
        f"- overall: `{payload['overall_status']}`",
        "",
        "| Check | Status | Detail | Evidence |",
        "|---|---|---|---|",
    ]
    for check in payload["checks"]:
        lines.append(f"| {check['check_id']} | {check['status']} | {check['detail']} | `{check['evidence']}` |")
    lines.extend(
        [
            "",
            "`READY_FOR_HUMAN_REVIEW` means engineering evidence is complete while video and reviewer acceptance remain pending.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("output/evidence/e07"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    checks = build_checks(root)
    failed = [check for check in checks if check.status == "FAIL"]
    pending = [check for check in checks if check.status == "PENDING"]
    overall = "FAIL" if failed else "READY_FOR_HUMAN_REVIEW" if pending else "PASS"
    payload = {
        "schema_version": "e07-judge-demo-preflight/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall,
        "counts": {
            "pass": sum(check.status == "PASS" for check in checks),
            "pending": len(pending),
            "fail": len(failed),
        },
        "checks": [asdict(check) for check in checks],
    }
    (output / "preflight.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(output / "preflight.md", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

