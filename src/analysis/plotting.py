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
            "savefig.pad_inches": 0.08,
            "axes.edgecolor": "black",
            "axes.labelcolor": "black",
            "axes.linewidth": 0.8,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9,
            "xtick.color": "black",
            "ytick.color": "black",
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "font.size": 9,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "grid.color": "0.75",
            "grid.linewidth": 0.45,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save_figure(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
