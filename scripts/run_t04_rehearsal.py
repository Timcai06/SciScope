"""Run the fixed T04 remote SSE rehearsal and write auditable evidence.

The script intentionally uses only the Python standard library. It never reads
or writes model credentials; it talks to an already configured local backend.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_CLAIM = "检索增强生成能够降低大语言模型回答中的幻觉风险"


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - fixed local URL
        return json.load(response)


def run_stream(base_url: str, claim: str, session_id: str, output: Path) -> dict[str, Any]:
    payload = {
        "question": f"请核查：{claim}，并给出支持、反驳或证据不足的审慎结论。",
        "history": [],
        "session_id": session_id,
    }
    request = urllib.request.Request(
        f"{base_url}/api/agent/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started_wall = datetime.now(UTC)
    started = time.perf_counter()
    first_event_seconds: float | None = None
    raw_lines: list[str] = []
    frames: list[dict[str, Any]] = []
    done = False
    http_status: int | None = None

    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - fixed local URL
            http_status = response.status
            for raw in response:
                line = raw.decode("utf-8", errors="replace")
                raw_lines.append(line)
                stripped = line.strip()
                if not stripped.startswith("data:"):
                    continue
                data = stripped[5:].strip()
                if data == "[DONE]":
                    done = True
                    continue
                if first_event_seconds is None:
                    first_event_seconds = time.perf_counter() - started
                try:
                    frame = json.loads(data)
                except json.JSONDecodeError:
                    frame = {"type": "parse_error", "payload": data}
                frames.append(frame)
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        raw_lines.append(exc.read().decode("utf-8", errors="replace"))

    total_seconds = time.perf_counter() - started
    output.write_text("".join(raw_lines), encoding="utf-8")

    tool_calls = [
        frame.get("payload", {}).get("name")
        for frame in frames
        if frame.get("type") == "tool_call" and isinstance(frame.get("payload"), dict)
    ]
    final_frame = next((frame for frame in reversed(frames) if frame.get("type") == "final"), {})
    final_meta = final_frame.get("meta") if isinstance(final_frame.get("meta"), dict) else {}
    structured = final_meta.get("structured_answer")
    if not isinstance(structured, dict):
        structured = {}
    citations = structured.get("citations")
    if not isinstance(citations, list):
        citations = []

    return {
        "session_id": session_id,
        "started_at": started_wall.isoformat(),
        "http_status": http_status,
        "first_event_seconds": round(first_event_seconds, 3) if first_event_seconds is not None else None,
        "total_seconds": round(total_seconds, 3),
        "done": done,
        "event_count": len(frames),
        "event_types": [frame.get("type") for frame in frames],
        "tool_calls": tool_calls,
        "stop_reason": final_meta.get("stop_reason"),
        "model": final_meta.get("model"),
        "structured_status": structured.get("status"),
        "citation_compliance": structured.get("citation_compliance"),
        "citation_count": len(citations),
        "has_error": any(frame.get("type") in {"error", "parse_error"} for frame in frames),
        "raw_sse": output.name,
    }


def write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# T04 remote canonical rehearsal",
        "",
        f"- commit: `{manifest['commit']}`",
        f"- backend: `{manifest['base_url']}`",
        f"- claim: {manifest['claim']}",
        f"- generated: `{manifest['generated_at']}`",
        "",
        "| Run | HTTP | First event (s) | Total (s) | Model | Status | Citations | Tools | DONE | Error |",
        "|---:|---:|---:|---:|---|---|---:|---|---|---|",
    ]
    for index, run in enumerate(manifest["runs"], start=1):
        lines.append(
            "| {index} | {http} | {first} | {total} | {model} | {status} | {citations} | {tools} | {done} | {error} |".format(
                index=index,
                http=run["http_status"],
                first=run["first_event_seconds"],
                total=run["total_seconds"],
                model=run["model"],
                status=run["structured_status"],
                citations=run["citation_count"],
                tools=", ".join(filter(None, run["tool_calls"])),
                done="yes" if run["done"] else "no",
                error="yes" if run["has_error"] else "no",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--claim", default=DEFAULT_CLAIM)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    health = get_json(f"{args.base_url}/healthz")
    readiness = get_json(f"{args.base_url}/readyz")
    (args.output_dir / "healthz.json").write_text(json.dumps(health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "readyz.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run_results = []
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for index in range(1, args.runs + 1):
        run_results.append(
            run_stream(
                args.base_url,
                args.claim,
                f"t04-{stamp}-run-{index}",
                args.output_dir / f"run-{index}.sse",
            )
        )

    manifest = {
        "schema_version": "t04-rehearsal/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": args.commit,
        "base_url": args.base_url,
        "claim": args.claim,
        "runner": {"python": platform.python_version(), "sequential": True},
        "healthz": health,
        "readyz": readiness,
        "runs": run_results,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.output_dir / "summary.md", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(run["http_status"] == 200 and run["done"] and not run["has_error"] for run in run_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
