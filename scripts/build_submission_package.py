from __future__ import annotations

import csv
import argparse
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "submission"
STAGE_DIR = OUT_DIR / "SciScope_submission"
ZIP_PATH = OUT_DIR / "SciScope_submission.zip"
MANIFEST_CSV = OUT_DIR / "SciScope_submission_manifest.csv"


@dataclass(frozen=True)
class Include:
    path: str
    required: bool = True


INCLUDES = [
    Include("README.md"),
    Include("交付说明.md"),
    Include("Makefile"),
    Include("docs/runbook.md"),
    Include("docs/final_submission_checklist.md"),
    Include("docs/submission_manifest.md"),
    Include("docs/mcp.md"),
    Include("docs/data-agent-boundary.md"),
    Include("docs/project_structure.md"),
    Include("docs/competition"),
    Include("docs/examples"),
    Include("configs"),
    Include("infra"),
    Include("src"),
    Include("backend"),
    Include("data_pipeline"),
    Include("tui"),
    Include("models/trends"),
    Include("models/recommend"),
    Include("output/graphs"),
    Include("output/eval"),
    Include("data/raw_canonical"),
    Include("data/analysis"),
    Include("data/processed"),
    Include("output/assets/sciscope_data_report"),
    Include("output/assets/sciscope_project_report"),
    Include("output/pdf/sciscope_data_report/sciscope_data_report.pdf"),
    Include("output/pdf/sciscope_project_report/sciscope_project_report.pdf"),
]

LARGE_MODEL_INCLUDES = [
    Include("models/embedder_local", required=False),
    Include("models/llm_local", required=False),
]


EXCLUDE_DIRS = {
    ".git",
    ".cache",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".next",
    "dist",
    "build",
    "tmp",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".DS_Store",
    ".log",
    ".aux",
    ".fdb_latexmk",
    ".fls",
    ".synctex.gz",
    ".xdv",
}

EXCLUDE_FILES = {
    ".env",
    ".env.local",
    "tsconfig.tsbuildinfo",
}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    return any(path.name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES)


def copy_item(src: Path, dest: Path) -> list[Path]:
    copied: list[Path] = []
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return [dest]

    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if should_skip(rel):
            continue
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied.append(target)
    return copied


def write_manifest(rows: list[tuple[Path, int]]) -> None:
    MANIFEST_CSV.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["path", "bytes"])
        for path, size in sorted(rows, key=lambda row: str(row[0])):
            writer.writerow([path.as_posix(), size])


def make_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in STAGE_DIR.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(OUT_DIR))
        zf.write(MANIFEST_CSV, MANIFEST_CSV.relative_to(OUT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SciScope whitelist submission package.")
    parser.add_argument(
        "--include-large-models",
        action="store_true",
        help="include local embedder/LLM directories if present",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate inputs and print the planned include list without copying or zipping",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    includes = list(INCLUDES)
    if args.include_large_models:
        includes.extend(LARGE_MODEL_INCLUDES)

    if args.dry_run:
        missing_required = []
        print("planned includes:")
        for include in includes:
            src = ROOT / include.path
            status = "ok" if src.exists() else ("missing-required" if include.required else "missing-optional")
            print(f"- {include.path} [{status}]")
            if include.required and not src.exists():
                missing_required.append(include.path)
        if not args.include_large_models:
            print("large models: skipped by default; pass --include-large-models to include them")
        return 1 if missing_required else 0

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    copied_rows: list[tuple[Path, int]] = []

    for include in includes:
        src = ROOT / include.path
        if not src.exists():
            message = f"missing {'required' if include.required else 'optional'}: {include.path}"
            if include.required:
                print(f"ERROR: {message}", file=sys.stderr)
                return 1
            warnings.append(message)
            continue

        dest = STAGE_DIR / include.path
        copied = copy_item(src, dest)
        for path in copied:
            copied_rows.append((path.relative_to(STAGE_DIR), path.stat().st_size))

    write_manifest(copied_rows)
    shutil.copy2(MANIFEST_CSV, STAGE_DIR / "submission_manifest.csv")
    make_zip()

    print(f"staged: {STAGE_DIR}")
    print(f"zip: {ZIP_PATH}")
    print(f"manifest: {MANIFEST_CSV}")
    print(f"files: {len(copied_rows)}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")
    if not args.include_large_models:
        print("large models skipped: use --include-large-models if the platform allows a larger package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
