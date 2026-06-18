#!/usr/bin/env python3
"""
X Profile Header Image Generator
Output: REVENUE/X/cards/x_header.png (1500x500px)
Theme: Dark gradient | purple + teal | no company names
"""

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ─── PATHS ────────────────────────────────────────────────────────────────────

OUT_DIR = Path("/Users/mboyajeffers/Claude_Projects/REVENUE/X/cards")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "x_header.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG_LEFT  = "#0a0f1e"
BG_RIGHT = "#0d1f35"
PURPLE   = "#a855f7"
TEAL     = "#2d9596"
WHITE    = "#f1f5f9"
DIM      = "#64748b"
GRID_CLR = "#0f1a2e"


def draw_header():
    # 1500x500 at 100dpi = 15x5 inches
    fig, ax = plt.subplots(figsize=(15, 5), dpi=100)
    fig.patch.set_facecolor(BG_LEFT)
    ax.set_facecolor(BG_LEFT)
    ax.set_xlim(0, 1500)
    ax.set_ylim(0, 500)
    ax.axis("off")

    # ── BACKGROUND GRADIENT (left→right via polygon fill) ─────────────────────
    # Simulate gradient with horizontal band
    gradient = np.linspace(0, 1, 300)
    for i, alpha in enumerate(gradient):
        color = (
            0.05 + 0.08 * alpha,
            0.08 + 0.10 * alpha,
            0.15 + 0.12 * alpha,
        )
        ax.axvspan(i * 5, (i + 1) * 5, ymin=0, ymax=1, color=color, alpha=1)

    # ── SUBTLE GRID LINES (data aesthetic) ────────────────────────────────────
    for x in range(0, 1500, 75):
        ax.axvline(x, color=GRID_CLR, linewidth=0.4, alpha=0.5, zorder=1)
    for y in range(0, 500, 50):
        ax.axhline(y, color=GRID_CLR, linewidth=0.4, alpha=0.5, zorder=1)

    # ── ACCENT BARS ───────────────────────────────────────────────────────────
    # Purple vertical bar on left
    ax.add_patch(mpatches.Rectangle((0, 0), 6, 500, color=PURPLE, alpha=0.8, zorder=3))
    # Teal horizontal bar on bottom
    ax.add_patch(mpatches.Rectangle((0, 0), 1500, 4, color=TEAL, alpha=0.8, zorder=3))

    # ── MAIN TITLE ────────────────────────────────────────────────────────────
    ax.text(80, 310, "Automated Analytics",
            fontsize=52, fontweight="bold", color=WHITE,
            va="center", ha="left", zorder=4,
            fontfamily="DejaVu Sans")

    # ── SUBTITLE ──────────────────────────────────────────────────────────────
    ax.text(80, 240, "Finance  ·  Crypto  ·  Energy",
            fontsize=22, color=TEAL, va="center", ha="left", zorder=4,
            fontfamily="DejaVu Sans", fontstyle="italic")

    # ── CHIPS (3 feature labels) ───────────────────────────────────────────────
    chips = ["LIVE API DATA", "PRODUCTION-GRADE", "AUTOMATED PDF REPORTS"]
    chip_colors = [PURPLE, TEAL, "#3b82f6"]
    x_start = 80
    chip_y = 160
    for i, (chip, color) in enumerate(zip(chips, chip_colors)):
        # measure text width approximately (8px per char at fontsize 11)
        chip_w = len(chip) * 9 + 24
        rect = mpatches.FancyBboxPatch(
            (x_start, chip_y - 15), chip_w, 32,
            boxstyle="round,pad=3",
            facecolor=color, edgecolor="none",
            alpha=0.25, zorder=4
        )
        ax.add_patch(rect)
        border = mpatches.FancyBboxPatch(
            (x_start, chip_y - 15), chip_w, 32,
            boxstyle="round,pad=3",
            facecolor="none", edgecolor=color,
            linewidth=1, alpha=0.7, zorder=5
        )
        ax.add_patch(border)
        ax.text(x_start + chip_w / 2, chip_y + 1, chip,
                fontsize=10, fontweight="bold", color=color,
                va="center", ha="center", zorder=6)
        x_start += chip_w + 18

    # ── GITHUB LINK (bottom right) ────────────────────────────────────────────
    ax.text(1480, 28, "github.com/mboyajeffers/data-reports-showcase",
            fontsize=10, color=DIM, va="center", ha="right", zorder=4)

    # ── DECORATIVE METRIC BUBBLES (right side) ────────────────────────────────
    bubbles = [
        (1150, 370, "Finance", TEAL, 0.12),
        (1280, 290, "Crypto", PURPLE, 0.15),
        (1380, 390, "Energy", "#f59e0b", 0.10),
        (1100, 250, "Equities", "#3b82f6", 0.09),
    ]
    for bx, by, label, color, alpha in bubbles:
        circle = plt.Circle((bx, by), 55, color=color, alpha=alpha, zorder=2)
        ax.add_patch(circle)
        ax.text(bx, by, label, fontsize=9, color=color, alpha=0.6,
                va="center", ha="center", zorder=3, fontweight="bold")

    plt.tight_layout(pad=0)
    plt.savefig(OUT_PATH, dpi=100, bbox_inches="tight",
                facecolor=BG_LEFT, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    draw_header()
    print("Done.")
