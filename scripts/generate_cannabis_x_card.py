#!/usr/bin/env python3
"""
NYC Cannabis Analytics — X card generator
Output: REVENUE/X/cards/cannabis_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #0d1520 background | #c49a2a gold | #1e2d45 navy (cannabis brand palette)
Data: static 280E/excise calculations + yfinance (MSO stocks)
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import yfinance as yf

from card_spec import (
    FONT_TITLE, FONT_HEADLINE, FONT_HANDLE,
    FONT_LABEL, FONT_SMALL, FONT_TINY, FONT_MICRO,
    GS_TOP, GS_BOTTOM, GS_WSPACE,
    HDR_TITLE_Y, HDR_HEADLINE_Y, HDR_STAT_Y, HDR_HANDLE_Y,
    FOOTER_Y, FOOTER_LINE_Y, MARGIN_LEFT, MARGIN_RIGHT,
)
from card_validator import detect_and_fix_overlaps


# ─── PATHS ────────────────────────────────────────────────────────────────────

OUT_DIR   = Path(__file__).parent.parent / "cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)
_now_utc  = datetime.now(timezone.utc)
TODAY     = _now_utc.strftime("%Y-%m-%d")
TIMESTAMP = _now_utc.strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"cannabis_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG           = "#0a0e14"   # site --bg-primary
GOLD         = "#f59e0b"   # cannabis accent: premium gold (matches PDF branding, pops on dark bg)
GOLD_DIM     = "#92400e"   # muted gold / gradient depth
RED          = "#ef4444"
AMBER        = "#f59e0b"
GREY         = "#64748b"   # site --text-muted
WHITE        = "#f1f5f9"   # site --text-primary
DIM          = "#94a3b8"   # site --text-secondary
CARD_BG      = "#1a2130"   # site --bg-card
PANEL_BORDER = "#2a3441"   # site --border-color

# ─── 280E MATH ────────────────────────────────────────────────────────────────
# Federal tax rate: 21%
# Gross margin assumption: 45%
# 280E rule: only COGS deductible (not operating expenses)
# Normal company: net after deductions = ~20% of revenue → 21% * 20% = 4.2% effective
# Cannabis under 280E: taxable = gross profit (revenue - COGS) = 45% of revenue
#   → federal tax = 21% * 45% = 9.45% of revenue
# Normal federal tax (comparable non-cannabis): 21% * 20% = 4.2% of revenue
# 280E penalty = (9.45% - 4.2%) of revenue = 5.25% of revenue
# BUT: for the label we show the dollar penalty per tier at GROSS PROFIT level

FED_RATE   = 0.21
MARGIN     = 0.45   # gross margin (revenue - COGS) / revenue
NORMAL_NET = 0.20   # net income margin for a normal company pre-tax

REVENUE_TIERS = [500_000, 1_000_000, 2_000_000, 4_000_000]

def compute_280e_penalty(revenue):
    """280E extra federal tax vs normal company at same revenue."""
    gross_profit  = revenue * MARGIN
    _cogs         = revenue * (1 - MARGIN)
    # 280E: taxed on gross profit (no operating expense deduction)
    cannabis_tax  = gross_profit * FED_RATE
    # Normal: taxed on net income (~20% of revenue)
    normal_income = revenue * NORMAL_NET
    normal_tax    = normal_income * FED_RATE
    return cannabis_tax - normal_tax

# ─── NY EXCISE TIERS (NY OCM public regulations) ──────────────────────────────
# Cannabis Potency Tax (enacted 2022, effective 2024):
#   Flower/pre-roll: $0.005/mg THC if <35mg; $0.0125/mg if 35-80mg; $0.022/mg if >80mg
# Example: 50mg cartridge × 1,000 units → $0.0125 × 50 × 1,000 = $625.00

NY_EXCISE_TIERS = [
    ("<35mg THC",  "$0.005/mg",  "Tier 1"),
    ("35–80mg",    "$0.0125/mg", "Tier 2"),
    (">80mg THC",  "$0.022/mg",  "Tier 3"),
]
EXCISE_EXAMPLE = {
    "label": "50mg × 1,000 units",
    "calc":  "1,000 × 50 × $0.0125",
    "result": "$625.00",
}

# ─── MSO STOCKS ───────────────────────────────────────────────────────────────

MSO_TICKERS = [
    ("MJ",    "ETFMG Alt Harvest ETF"),
    ("CURLF", "Curaleaf"),
    ("GTBIF", "Green Thumb"),
    ("IIPR",  "Innovative Industrial REIT"),   # facility expansion velocity signal
]

# Federal rescheduling status (update when DEA Final Rule publishes)
FEDERAL_STATUS = "Schedule III: DEA Final Rule pending"
FEDERAL_COLOR_KEY = "amber"   # switch to "gold" when rescheduled


def fetch_5d(ticker, retries=3):
    for i in range(retries):
        try:
            h = yf.Ticker(ticker).history(period="10d")
            if h.empty or len(h) < 2:
                raise ValueError("insufficient data")
            c = h["Close"].dropna().tolist()
            ret = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else (c[-1] - c[0]) / c[0] * 100
            return c[-1], ret
        except Exception:
            if i < retries - 1:
                time.sleep(2)
    return None, None


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(mso_data):
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    # Top accent stripe
    fig.add_artist(plt.Line2D([0, 1], [0.993, 0.993],
                              transform=fig.transFigure, color=GOLD, linewidth=2.5,
                              solid_capstyle="butt", zorder=10))

    gs = gridspec.GridSpec(1, 3, figure=fig,
                           width_ratios=[3.8, 3.2, 3.0],
                           left=0.02, right=0.98,
                           top=GS_TOP, bottom=GS_BOTTOM, wspace=GS_WSPACE)
    ax_bars  = fig.add_subplot(gs[0, 0])
    ax_excise = fig.add_subplot(gs[0, 1])
    ax_mso   = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_excise, ax_mso]:
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values():
            sp.set_edgecolor(PANEL_BORDER)

    ax_excise.axis("off")

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, HDR_TITLE_Y, f"NYC Cannabis Analytics — {TODAY}",
             fontsize=FONT_TITLE, fontweight="bold", color=WHITE, va="top")
    fig.text(MARGIN_LEFT, HDR_HEADLINE_Y,
             "280E federal penalty · NY excise tiers · MSO market pulse",
             fontsize=FONT_HEADLINE, color=GOLD, va="top")
    fig.text(MARGIN_RIGHT, HDR_STAT_Y, "OCM Audits ACTIVE",
             fontsize=FONT_HEADLINE, color=AMBER, va="top", ha="right", fontweight="bold")
    fig.text(MARGIN_RIGHT, HDR_HANDLE_Y, "@Mboya_Jeffers",
             fontsize=FONT_HANDLE, color=GOLD, va="top", ha="right", fontweight="bold")

    # ── LEFT: 280E PENALTY BARS ───────────────────────────────────────────────
    penalties = [compute_280e_penalty(r) for r in REVENUE_TIERS]
    labels    = ["$500K rev", "$1M rev", "$2M rev", "$4M rev"]
    colors    = [AMBER, RED, RED, RED]
    colors[0] = AMBER

    ax_bars.set_facecolor(CARD_BG)
    y_pos = range(len(labels))
    _bars = ax_bars.barh(list(y_pos), penalties, color=colors, height=0.62, alpha=0.85)
    ax_bars.set_yticks(list(y_pos))
    ax_bars.set_yticklabels(labels, fontsize=FONT_SMALL, color=WHITE)
    ax_bars.tick_params(axis="x", labelsize=6.5, colors=DIM)
    ax_bars.set_title("280E Extra Federal Tax vs. Normal Co.", fontsize=FONT_HANDLE, color=DIM, pad=6)
    ax_bars.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"${x/1000:.0f}K")
    )
    ax_bars.grid(axis="x", color="#1a2030", linewidth=0.5, alpha=0.7)

    xmax = max(penalties) if penalties else 1
    buf  = xmax * 0.28
    ax_bars.set_xlim(0, xmax + buf)
    for i, (v, c) in enumerate(zip(penalties, colors)):
        off = xmax * 0.03
        ax_bars.text(v + off, i, f"${v:,.0f}",
                     va="center", ha="left", fontsize=FONT_LABEL, color=c, fontweight="bold")

    # Annotation
    ax_bars.text(0.5, -0.14,
                 "Assumes 45% gross margin · 21% fed rate · 280E = no op-ex deduction",
                 fontsize=FONT_MICRO, color=GREY, transform=ax_bars.transAxes,
                 ha="center", style="italic")

    # ── CENTER: NY EXCISE RATE TABLE ──────────────────────────────────────────
    ax_excise.axis("off")
    ax_excise.set_title("NY Cannabis Potency Tax (OCM)", fontsize=FONT_HANDLE, color=DIM, pad=6)

    # Column headers
    ax_excise.text(0.04, 0.92, "Potency Tier", fontsize=FONT_LABEL, color=DIM,
                   transform=ax_excise.transAxes, va="top", fontweight="bold")
    ax_excise.text(0.58, 0.92, "Rate/mg THC", fontsize=FONT_LABEL, color=DIM,
                   transform=ax_excise.transAxes, va="top", ha="center", fontweight="bold")
    ax_excise.text(0.96, 0.92, "Tier", fontsize=FONT_LABEL, color=DIM,
                   transform=ax_excise.transAxes, va="top", ha="right", fontweight="bold")

    # Divider
    ax_excise.add_artist(plt.Line2D([0.02, 0.98], [0.90, 0.90],
                                    transform=ax_excise.transAxes,
                                    color=PANEL_BORDER, linewidth=0.7))

    row_y = [0.77, 0.62, 0.47]
    row_colors = [GOLD, AMBER, RED]
    for (tier_range, rate, tier_label), y, rc in zip(NY_EXCISE_TIERS, row_y, row_colors):
        ax_excise.text(0.04, y, tier_range, fontsize=FONT_SMALL, color=WHITE,
                       transform=ax_excise.transAxes, va="top")
        ax_excise.text(0.58, y, rate, fontsize=FONT_HEADLINE, color=rc, fontweight="bold",
                       transform=ax_excise.transAxes, va="top", ha="center")
        ax_excise.text(0.96, y, tier_label, fontsize=FONT_TINY, color=DIM,
                       transform=ax_excise.transAxes, va="top", ha="right")
        ax_excise.add_artist(plt.Line2D([0.02, 0.98], [y - 0.07, y - 0.07],
                                        transform=ax_excise.transAxes,
                                        color=PANEL_BORDER, linewidth=0.5))

    # Example calc box
    rect = FancyBboxPatch((0.04, 0.14), 0.92, 0.25,
                          boxstyle="round,pad=0.02",
                          facecolor="#0d1520", edgecolor=GOLD, linewidth=0.9,
                          transform=ax_excise.transAxes, clip_on=False)
    ax_excise.add_patch(rect)
    ax_excise.text(0.5, 0.38, "Example Calc",
                   fontsize=FONT_TINY, color=GOLD, transform=ax_excise.transAxes,
                   ha="center", va="top", fontweight="bold")
    ax_excise.text(0.5, 0.31, EXCISE_EXAMPLE["label"],
                   fontsize=FONT_LABEL, color=WHITE, transform=ax_excise.transAxes,
                   ha="center", va="top")
    ax_excise.text(0.5, 0.24, EXCISE_EXAMPLE["calc"],
                   fontsize=FONT_TINY, color=DIM, transform=ax_excise.transAxes,
                   ha="center", va="top")
    ax_excise.text(0.5, 0.17, f"= {EXCISE_EXAMPLE['result']}",
                   fontsize=FONT_SMALL, color=GOLD, transform=ax_excise.transAxes,
                   ha="center", va="top", fontweight="bold")
    ax_excise.text(0.5, 0.05, "Source: NY OCM public regulations",
                   fontsize=FONT_MICRO, color=GREY, transform=ax_excise.transAxes,
                   ha="center", style="italic")

    # ── RIGHT: MSO STOCKS + COMPLIANCE/FEDERAL BADGE ──────────────────────────
    ax_mso.axis("off")
    ax_mso.set_title("MSO + REIT Market Pulse (5-Day)", fontsize=FONT_SMALL, color=DIM, pad=6)

    y_cur = 0.87
    for (sym, name), (price, ret) in zip(MSO_TICKERS, mso_data):
        if ret is not None:
            rc = GOLD if ret >= 0 else RED
            ax_mso.text(0.06, y_cur, f"{sym}", fontsize=FONT_SMALL, color=WHITE,
                        transform=ax_mso.transAxes, va="top", fontweight="bold")
            ax_mso.text(0.94, y_cur, f"{ret:+.1f}%", fontsize=FONT_HANDLE, color=rc,
                        transform=ax_mso.transAxes, va="top", ha="right", fontweight="bold")
            ax_mso.text(0.06, y_cur - 0.06, name, fontsize=FONT_TINY, color=GREY,
                        transform=ax_mso.transAxes, va="top")
            if price is not None:
                ax_mso.text(0.94, y_cur - 0.06, f"${price:.2f}", fontsize=FONT_SMALL, color=DIM,
                            transform=ax_mso.transAxes, va="top", ha="right")
        else:
            ax_mso.text(0.06, y_cur, f"{sym}", fontsize=FONT_SMALL, color=GREY,
                        transform=ax_mso.transAxes, va="top")
            ax_mso.text(0.94, y_cur, "N/A", fontsize=FONT_HANDLE, color=GREY,
                        transform=ax_mso.transAxes, va="top", ha="right")
        ax_mso.add_artist(plt.Line2D([0.03, 0.97], [y_cur - 0.13, y_cur - 0.13],
                                     transform=ax_mso.transAxes,
                                     color=PANEL_BORDER, linewidth=0.5))
        y_cur -= 0.17

    # Two-line badge: OCM Audits + Federal Schedule status
    badge_y = y_cur - 0.02
    rect2 = FancyBboxPatch((0.04, badge_y - 0.24), 0.92, 0.26,
                           boxstyle="round,pad=0.02",
                           facecolor="#1a1000", edgecolor=AMBER, linewidth=1.1,
                           transform=ax_mso.transAxes, clip_on=False)
    ax_mso.add_patch(rect2)
    ax_mso.text(0.5, badge_y, "OCM Audits ACTIVE",
                fontsize=FONT_SMALL, color=AMBER, transform=ax_mso.transAxes,
                ha="center", va="top", fontweight="bold")
    ax_mso.text(0.5, badge_y - 0.09, "Metrc recon = #1 trigger",
                fontsize=FONT_SMALL, color=DIM, transform=ax_mso.transAxes,
                ha="center", va="top")
    ax_mso.text(0.5, badge_y - 0.17, FEDERAL_STATUS,
                fontsize=FONT_SMALL, color=GOLD, transform=ax_mso.transAxes,
                ha="center", va="top", style="italic")

    ax_mso.text(0.5, 0.02, "Source: Yahoo Finance",
                fontsize=FONT_MICRO, color=GREY, transform=ax_mso.transAxes,
                ha="center", style="italic")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, FOOTER_Y,
             f"Source: NY OCM (public regulations) · Yahoo Finance  |  {TIMESTAMP}",
             fontsize=FONT_SMALL, color=GREY, va="top")
    fig.text(MARGIN_RIGHT, FOOTER_Y, "@Mboya_Jeffers  |  Not legal/tax advice",
             fontsize=FONT_SMALL, color=AMBER, va="top", ha="right")
    fig.add_artist(plt.Line2D([MARGIN_LEFT, MARGIN_RIGHT], [FOOTER_LINE_Y, FOOTER_LINE_Y],
                              transform=fig.transFigure, color=PANEL_BORDER, linewidth=0.8))

    
    detect_and_fix_overlaps(fig)
    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching MSO stock data...")
    mso_data = []
    for sym, name in MSO_TICKERS:
        print(f"  {sym}...")
        price, ret = fetch_5d(sym)
        mso_data.append((price, ret))
        time.sleep(0.3)

    print("Drawing cannabis card...")
    draw_card(mso_data)
    print("Done.")


if __name__ == "__main__":
    main()
