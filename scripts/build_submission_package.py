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
SOURCE_STAGE = OUT_DIR / "SciScope_source"
DATA_STAGE = OUT_DIR / "SciScope_data"
SOURCE_ZIP = OUT_DIR / "SciScope_source.zip"
DATA_ZIP = OUT_DIR / "SciScope_data.zip"
SOURCE_MANIFEST = OUT_DIR / "SciScope_source_manifest.csv"
DATA_MANIFEST = OUT_DIR / "SciScope_data_manifest.csv"


@dataclass(frozen=True)
class Include:
    path: str
    required: bool = True


# 源代码包：代码 + 文档 + 报告 PDF（不含数据/模型资产）
SOURCE_INCLUDES = [
    Include("README.md"),
    Include("交付说明.md"),
    Include("Makefile"),
    Include("docs/README.md"),
    Include("docs/operations/runbook.md"),
    Include("docs/reports/final_submission_checklist.md"),
    Include("docs/reports/submission_manifest.md"),
    Include("docs/developer/mcp.md"),
    Include("docs/architecture/data-agent-boundary.md"),
    Include("docs/architecture/project_structure.md"),
    Include("docs/release"),
    Include("docs/competition"),
    Include("docs/examples"),
    Include(".sciscope/skills"),
    Include("scripts/agent_smoke.py"),
    Include("scripts/build_submission_package.py"),
    Include("configs"),
    Include("infra"),
    Include("src"),
    Include("backend"),
    Include("src/data_contracts"),
    Include("tui"),
    Include("models/trends"),
    Include("models/recommend"),
    Include("output/pdf/sciscope_data_report/sciscope_data_report.pdf"),
    Include("output/pdf/sciscope_project_report/sciscope_project_report.pdf"),
]

# 数据资产包：语料、分析产物、图谱/评测、图表资产
DATA_INCLUDES = [
    Include("output/graphs"),
    Include("output/eval"),
    Include("data/raw_canonical"),
    Include("data/analysis"),
    Include("data/processed"),
    Include("output/assets/sciscope_data_report"),
    Include("output/assets/sciscope_project_report"),
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


def write_manifest(rows: list[tuple[Path, int]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["path", "bytes"])
        for p, size in sorted(rows, key=lambda row: str(row[0])):
            writer.writerow([p.as_posix(), size])


def make_zip(stage: Path, zip_path: Path, manifest: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in stage.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(OUT_DIR))
        zf.write(manifest, manifest.relative_to(OUT_DIR))


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


def build_group(
    name: str,
    includes: list[Include],
    stage: Path,
    zip_path: Path,
    manifest_path: Path,
) -> tuple[list[str], int]:
    """打包一组（source / data）。返回 (warnings, 文件数)。"""
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    copied_rows: list[tuple[Path, int]] = []

    for include in includes:
        src = ROOT / include.path
        if not src.exists():
            message = f"missing {'required' if include.required else 'optional'}: {include.path}"
            if include.required:
                print(f"ERROR: {message}", file=sys.stderr)
                raise SystemExit(1)
            warnings.append(message)
            continue

        dest = stage / include.path
        copied = copy_item(src, dest)
        for path in copied:
            copied_rows.append((path.relative_to(stage), path.stat().st_size))

    write_manifest(copied_rows, manifest_path)
    shutil.copy2(manifest_path, stage / "submission_manifest.csv")
    make_zip(stage, zip_path, manifest_path)

    print(f"[{name}] staged: {stage}")
    print(f"[{name}] zip: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")
    print(f"[{name}] manifest: {manifest_path}")
    print(f"[{name}] files: {len(copied_rows)}")
    for warning in warnings:
        print(f"[{name}] warning: {warning}")
    return warnings, len(copied_rows)


def main() -> int:
    args = parse_args()
    source_includes = list(SOURCE_INCLUDES)
    data_includes = list(DATA_INCLUDES)
    if args.include_large_models:
        data_includes.extend(LARGE_MODEL_INCLUDES)

    if args.dry_run:
        missing_required = []
        print("planned includes:")
        for group, includes in (("source", source_includes), ("data", data_includes)):
            for include in includes:
                src = ROOT / include.path
                status = "ok" if src.exists() else ("missing-required" if include.required else "missing-optional")
                print(f"- [{group}] {include.path} [{status}]")
                if include.required and not src.exists():
                    missing_required.append(include.path)
        if not args.include_large_models:
            print("large models: skipped by default; pass --include-large-models to include them")
        return 1 if missing_required else 0

    build_group("source", source_includes, SOURCE_STAGE, SOURCE_ZIP, SOURCE_MANIFEST)
    build_group("data", data_includes, DATA_STAGE, DATA_ZIP, DATA_MANIFEST)

    if not args.include_large_models:
        print("large models skipped: use --include-large-models if the platform allows a larger package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
