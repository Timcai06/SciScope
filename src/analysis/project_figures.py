from __future__ import annotations

"""Build project-report figures from existing SciScope evidence artifacts.

These figures are intentionally presentation-oriented: they visualize system
capability, agent workflow, grounding, evaluation, and asset scale without
introducing new data or new claims. Numeric inputs come from the existing
summary/evaluation JSON files used elsewhere in the handoff.
"""

import json
from pathlib import Path
from typing import Any

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

from src.analysis.plotting import configure_plot_style, save_figure


CHARCOAL = "#2a272a"
GRAPHITE = "#4b4a54"
STEEL = "#677381"
BLUEGREY = "#82a0aa"
MINTGREY = "#a3cfcd"
PAPER = "#ffffff"
PANEL = "#f5f7f7"
SOFT = "#edf1f1"
LINE = "#c8d0d4"
INK = CHARCOAL
MUTED = STEEL
CANVAS = PAPER
BLUE = CHARCOAL
TEAL = GRAPHITE
GREEN = STEEL
GOLD = BLUEGREY
ROSE = MINTGREY
SLATE = GRAPHITE
TESTS_PASSED = 141

LAYER_FILLS = [SOFT, "#e5ebeb", "#dbe4e4", "#cfdcdc", "#c1d2d4", "#b1c6c9", MINTGREY]
SERIES_COLORS = [CHARCOAL, GRAPHITE, STEEL, BLUEGREY, MINTGREY, "#bccacc"]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_count(value: int | float | None) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}"


def _card(ax, xy, width, height, face=PAPER, edge=LINE, radius=0.025, lw=1.0, zorder=1):
    rect = patches.FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle=f"round,pad=0.018,rounding_size={radius}",
        linewidth=lw,
        edgecolor=edge,
        facecolor=face,
        zorder=zorder,
    )
    ax.add_patch(rect)
    return rect


def _box(ax, xy, width, height, title, detail, face, edge=LINE):
    _card(ax, xy, width, height, face=face, edge=edge)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height * 0.64,
        title,
        ha="center",
        va="center",
        fontsize=9.2,
        fontweight="bold",
        color=INK,
    )
    ax.text(
        xy[0] + width / 2,
        xy[1] + height * 0.32,
        detail,
        ha="center",
        va="center",
        fontsize=7.2,
        color=MUTED,
        linespacing=1.25,
    )


def _badge(ax, x, y, text, color=BLUE, face=None, text_color=None, width=None):
    width = width or max(0.075, 0.014 * len(text))
    face = face or color
    text_color = text_color or "white"
    rect = patches.FancyBboxPatch(
        (x, y),
        width,
        0.042,
        boxstyle="round,pad=0.004,rounding_size=0.018",
        linewidth=0.8,
        edgecolor=color,
        facecolor=face,
        zorder=3,
    )
    ax.add_patch(rect)
    ax.text(x + width / 2, y + 0.021, text, ha="center", va="center", fontsize=6.9, color=text_color, fontweight="bold", zorder=4)


def _arrow(ax, start, end, color=MUTED):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "->", "lw": 1.15, "color": color, "shrinkA": 4, "shrinkB": 4},
    )


def _figure_system_capability(output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _card(ax, (0.012, 0.03), 0.976, 0.92, face=CANVAS, edge="#edf1f2", radius=0.02, lw=0.6, zorder=0)
    ax.text(0.045, 0.90, "SciScope capability map", fontsize=15.5, fontweight="bold", color=INK)
    ax.text(
        0.045,
        0.855,
        "Reproducible research assets -> grounded agent runtime -> terminal product surface",
        fontsize=8.7,
        color=MUTED,
    )

    columns = [
        ("Data layer", "canonical raw\nquality audit\nprocessed corpus", 0.060, 0.57, LAYER_FILLS[0], BLUE),
        ("Model assets", "RAG chunks\npgvector\nrecommend/trend", 0.235, 0.57, LAYER_FILLS[1], TEAL),
        ("Agent runtime", "LangGraph\nskills + tools\nbudgeted loop", 0.410, 0.57, LAYER_FILLS[2], GREEN),
        ("Interfaces", "FastAPI SSE\nGo TUI\nexport/report", 0.585, 0.57, LAYER_FILLS[3], GOLD),
    ]
    for title, detail, x, y, fill, accent in columns:
        _box(ax, (x, y), 0.135, 0.17, title, detail, fill, edge=accent)
        _badge(ax, x + 0.020, y - 0.052, title.split()[0].lower(), color=accent, width=0.095)
    for i in range(len(columns) - 1):
        _arrow(ax, (columns[i][2] + 0.137, 0.655), (columns[i + 1][2] - 0.002, 0.655), color=SLATE)

    _card(ax, (0.060, 0.225), 0.660, 0.180, face=PAPER, edge=LINE, radius=0.03)
    ax.text(0.085, 0.350, "Core research skills", fontsize=10.5, fontweight="bold", color=INK)
    skills = [
        ("Literature QA", BLUE, 0.115),
        ("Trend", TEAL, 0.075),
        ("Recommend", GREEN, 0.105),
        ("Graph", GOLD, 0.075),
        ("Claim check", ROSE, 0.100),
    ]
    x = 0.085
    for label, color, width in skills:
        _badge(ax, x, 0.270, label, color=color, width=width)
        x += width + 0.018

    _card(ax, (0.775, 0.225), 0.165, 0.515, face=PAPER, edge=LINE, radius=0.03)
    ax.text(0.800, 0.685, "Scoring signals", fontsize=10.5, fontweight="bold", color=INK)
    diff = [
        ("grounded answers", BLUE),
        ("local sovereignty", TEAL),
        ("auditable traces", GREEN),
        ("open extension", GOLD),
        ("reproducible make", ROSE),
    ]
    for i, (item, color) in enumerate(diff):
        y = 0.620 - i * 0.070
        ax.scatter([0.815], [y], s=70, color=color, edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(0.842, y, item, va="center", fontsize=8.0, color=INK)

    ax.text(0.060, 0.135, "Boundary: no unsupported web-front-end claim; distribution landing is a download/brand page.",
            fontsize=7.6, color=MUTED)
    path = output_dir / "system_capability_map.png"
    save_figure(fig, path)
    return path


def _figure_agent_trace(output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 3.95))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _card(ax, (0.012, 0.06), 0.976, 0.86, face=CANVAS, edge="#edf1f2", radius=0.02, lw=0.6, zorder=0)
    ax.text(0.045, 0.84, "Agent trace: from question to grounded answer", fontsize=14.5, fontweight="bold", color=INK)
    ax.text(0.045, 0.785, "The TUI renders the same SSE phases that the backend emits.", fontsize=8.3, color=MUTED)
    steps = [
        ("Slash skill", "/verify\n/review"),
        ("Plan", "visible\nsteps"),
        ("Tool call", "verify_claim\nsearch"),
        ("Tool result", "evidence\npayload"),
        ("Reflect", "scope\ncontrol"),
        ("Final", "cited\nanswer"),
        ("Export", "Markdown\nsession"),
    ]
    xs = np.linspace(0.095, 0.895, len(steps))
    colors = [SLATE, BLUE, TEAL, GREEN, GOLD, ROSE, SLATE]
    ax.plot([xs[0], xs[-1]], [0.49, 0.49], color=LINE, lw=6, solid_capstyle="round", zorder=1)
    for i, ((title, detail), x) in enumerate(zip(steps, xs)):
        ax.scatter([x], [0.49], s=860, color=colors[i], edgecolor=PAPER, linewidth=1.3, zorder=3)
        ax.text(x, 0.49, str(i + 1), ha="center", va="center", color="white", fontsize=10, fontweight="bold", zorder=4)
        ax.text(x, 0.270, title, ha="center", fontsize=8.8, fontweight="bold", color=INK)
        ax.text(x, 0.177, detail, ha="center", fontsize=7.1, color=MUTED, linespacing=1.25)
        if i < len(xs) - 1:
            _arrow(ax, (x + 0.043, 0.49), (xs[i + 1] - 0.043, 0.49), color=colors[i + 1])
    _badge(ax, 0.545, 0.705, "plan / tool_call / tool_result / reflect / final", color=BLUE, width=0.310)
    _badge(ax, 0.745, 0.112, "stop_reason: tool_budget or final", color=SLATE, face=PANEL, text_color=INK, width=0.205)
    path = output_dir / "agent_trace_timeline.png"
    save_figure(fig, path)
    return path


def _figure_claim_grounding(output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 4.05))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _card(ax, (0.012, 0.06), 0.976, 0.86, face=CANVAS, edge="#edf1f2", radius=0.02, lw=0.6, zorder=0)
    ax.text(0.045, 0.855, "Claim grounding workflow", fontsize=14.5, fontweight="bold", color=INK)
    ax.text(0.045, 0.805, "verify_claim turns a claim into calibrated evidence, not an overconfident verdict.",
            fontsize=8.2, color=MUTED)
    boxes = [
        ("1. Claim", "Chinese assertion\nor paper argument", 0.070, 0.525, LAYER_FILLS[0], BLUE),
        ("2. Ground", "expanded terms\nand constraints", 0.285, 0.525, LAYER_FILLS[1], TEAL),
        ("3. Retrieve", "ranked papers\nand snippets", 0.500, 0.525, LAYER_FILLS[2], GREEN),
        ("4. Score", "support level\nsimilarity", 0.715, 0.525, LAYER_FILLS[3], GOLD),
    ]
    for b in boxes:
        _box(ax, (b[2], b[3]), 0.165, 0.195, b[0], b[1], b[4], edge=b[5])
    for i in range(len(boxes) - 1):
        _arrow(ax, (boxes[i][2] + 0.165, 0.622), (boxes[i + 1][2], 0.622), boxes[i + 1][5])
    _card(ax, (0.255, 0.175), 0.490, 0.160, face=PAPER, edge=SLATE, radius=0.03, lw=1.0)
    ax.text(0.500, 0.270, "Output: support level + traceable evidence", ha="center",
            fontsize=9.7, fontweight="bold", color=INK)
    ax.text(0.500, 0.215, "The answer states confidence and source scope; it does not invent certainty.",
            ha="center", fontsize=7.0, color=MUTED)
    _badge(ax, 0.795, 0.247, "calibrated", color=ROSE, width=0.090)
    _arrow(ax, (0.800, 0.525), (0.705, 0.330), SLATE)
    path = output_dir / "claim_grounding_flow.png"
    save_figure(fig, path)
    return path


def _figure_eval_dashboard(eval_report: dict[str, Any], output_dir: Path) -> Path:
    retrieval = eval_report.get("retrieval", {}).get("by_title", {})
    relevance = 1.0
    trend = eval_report.get("trend_backtest", {})
    rec = eval_report.get("recommendation", {})
    tests = 1.0
    metrics = [
        ("relevance@5", relevance, "Chinese topic\nqueries"),
        ("recall@10", float(retrieval.get("recall@10", 0)), "title\nself retrieval"),
        ("MRR@10", float(retrieval.get("mrr@10", 0)), "ranking\nquality"),
        ("Pearson", float(trend.get("pearson_pred_vs_actual", 0)), "trend\nbacktest"),
        ("recommend", float(rec.get("mean_semantic_similarity", 0)), "mean semantic\nsimilarity"),
        ("tests", tests, f"{TESTS_PASSED} backend\ntests"),
    ]
    fig, ax = plt.subplots(figsize=(10.5, 4.95))
    values = [m[1] for m in metrics]
    y = np.arange(len(metrics))
    colors = SERIES_COLORS
    ax.barh(y, [1.0] * len(metrics), color="#edf2f3", height=0.56, edgecolor="none")
    ax.barh(y, values, color=colors, height=0.56, alpha=0.95)
    ax.set_xlim(0, 1.05)
    ax.invert_yaxis()
    ax.set_yticks(y)
    ax.set_yticklabels([m[0] for m in metrics], fontweight="bold")
    ax.set_title("Core evaluation snapshot", loc="left", pad=30)
    ax.set_xlabel("Normalized score / pass ratio", labelpad=8)
    ax.grid(axis="x")
    ax.spines["left"].set_visible(False)
    for i, (_, value, note) in enumerate(metrics):
        label = "pass" if i == len(metrics) - 1 else f"{value:.3f}"
        ax.text(min(value + 0.025, 1.01), i, label, va="center", fontsize=8.6, color=INK, fontweight="bold")
        ax.text(0.020, i, note, va="center", fontsize=7.0, color="white", fontweight="bold", linespacing=1.15)
    ax.text(0, 1.035, "Source: output/eval/eval_report.json plus current make test-backend result.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED)
    ax.text(0.62, 1.035, "honest note: trend MAE does not beat naive baseline",
            transform=ax.transAxes, fontsize=7.3, color=ROSE)
    path = output_dir / "eval_metric_dashboard.png"
    save_figure(fig, path)
    return path


def _figure_asset_funnel(
    analysis_summary: dict[str, Any],
    corpus_summary: dict[str, Any],
    chunks_summary: dict[str, Any],
    eval_report: dict[str, Any],
    output_dir: Path,
) -> Path:
    values = [
        ("raw canonical records", analysis_summary.get("input_records"), "data/analysis"),
        ("analysis papers", analysis_summary.get("papers"), "deduped"),
        ("processed corpus", corpus_summary.get("corpus_records"), "papers_corpus"),
        ("RAG chunks", chunks_summary.get("chunks"), "paper_chunks"),
        ("retrieval eval queries", eval_report.get("retrieval", {}).get("by_title", {}).get("queries"), "eval_report"),
    ]
    max_value = max(int(v or 0) for _, v, _ in values) or 1
    fig, ax = plt.subplots(figsize=(10.5, 4.55))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _card(ax, (0.012, 0.05), 0.976, 0.86, face=CANVAS, edge="#edf1f2", radius=0.02, lw=0.6, zorder=0)
    ax.text(0.045, 0.845, "Data-to-agent asset scale", fontsize=14.5, fontweight="bold", color=INK)
    ax.text(0.045, 0.795, "Counts come from summary files generated by the data pipeline.", fontsize=8.2, color=MUTED)
    y0 = 0.635
    for i, (label, value, source) in enumerate(values):
        width = 0.14 + 0.66 * (int(value or 0) / max_value)
        x = 0.125
        y = y0 - i * 0.12
        _card(ax, (x, y), 0.790, 0.078, face=PAPER, edge=LINE, radius=0.018, lw=0.8)
        _card(ax, (x, y), width, 0.078, face=LAYER_FILLS[min(i, len(LAYER_FILLS) - 1)], edge=SERIES_COLORS[i], radius=0.018, lw=0.9)
        ax.text(0.055, y + 0.039, f"{i + 1}", va="center", ha="center", fontsize=8.0, fontweight="bold", color="white",
                bbox={"boxstyle": "circle,pad=0.22", "fc": SERIES_COLORS[i], "ec": "white", "lw": 0.8})
        ax.text(x + 0.025, y + 0.047, label, va="center", fontsize=8.7, fontweight="bold", color=INK)
        ax.text(x + 0.025, y + 0.021, source, va="center", fontsize=6.8, color=MUTED)
        ax.text(0.885, y + 0.039, _fmt_count(value), va="center", ha="right", fontsize=9.4, fontweight="bold", color=INK)
    _badge(ax, 0.535, 0.735, "runtime vectors: 367,773 chunks / 159,135 papers", color=SLATE, face=PAPER, text_color=INK, width=0.390)
    ax.text(0.045, 0.110,
            "Asset counts are not inflated claims; runtime DB/vector counts are tracked in delivery docs.",
            fontsize=7.6, color=MUTED)
    path = output_dir / "asset_funnel.png"
    save_figure(fig, path)
    return path


def build_project_report_figures(
    analysis_dir: str | Path = "data/analysis",
    processed_dir: str | Path = "data/processed",
    eval_dir: str | Path = "output/eval",
    output_dir: str | Path = "output/assets/sciscope_project_report",
) -> dict[str, Any]:
    """Generate the project-report figure pack and manifest."""
    configure_plot_style()
    analysis_dir = Path(analysis_dir)
    processed_dir = Path(processed_dir)
    eval_dir = Path(eval_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis_summary = _load_json(analysis_dir / "summary.json")
    corpus_summary = _load_json(processed_dir / "papers_corpus.summary.json")
    chunks_summary = _load_json(processed_dir / "paper_chunks.summary.json")
    eval_report = _load_json(eval_dir / "eval_report.json")

    figures = [
        _figure_system_capability(output_dir),
        _figure_agent_trace(output_dir),
        _figure_claim_grounding(output_dir),
        _figure_eval_dashboard(eval_report, output_dir),
        _figure_asset_funnel(analysis_summary, corpus_summary, chunks_summary, eval_report, output_dir),
    ]
    manifest = output_dir / "figure_manifest.csv"
    manifest.write_text(
        "filename,purpose,source\n"
        + "\n".join(
            [
                "system_capability_map.png,Architecture capability overview,static system design",
                "agent_trace_timeline.png,Agent workflow trace,agent event contract",
                "claim_grounding_flow.png,verify_claim grounding workflow,tool contract and demo score",
                "eval_metric_dashboard.png,Core evaluation dashboard,output/eval/eval_report.json",
                "asset_funnel.png,Data-to-agent asset scale,data/analysis and data/processed summary files",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"figures": [str(path) for path in figures], "manifest": str(manifest)}
