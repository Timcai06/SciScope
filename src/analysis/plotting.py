from __future__ import annotations

import os
from pathlib import Path


os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt


def configure_plot_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 160,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.12,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#2a272a",
            "axes.labelcolor": "#2a272a",
            "axes.linewidth": 0.7,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": "#2a272a",
            "ytick.color": "#2a272a",
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "font.size": 9,
            "font.family": "DejaVu Sans",
            "legend.frameon": False,
            "legend.fontsize": 8,
            "grid.color": "#d6dfe2",
            "grid.linewidth": 0.4,
            "grid.linestyle": "--",
            "lines.solid_capstyle": "round",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save_figure(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
