#!/usr/bin/env python3
"""
E-Commerce Sector Snapshot — X card generator
Output: cards/ecommerce_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #120c00 background | #d97706 amber
Data: yfinance (ecommerce stocks) + FRED (consumer sentiment UMCSENT)
"""

import csv
import io
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import yfinance as yf

from card_spec import (
    FONT_TITLE, FONT_HEADLINE, FONT_STAT, FONT_HANDLE,
    FONT_LABEL, FONT_VALUE, FONT_SMALL, FONT_TINY, FONT_MICRO,
    GS_TOP, GS_BOTTOM, GS_LEFT, GS_RIGHT, GS_WSPACE,
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
OUT_PATH  = OUT_DIR / f"ecommerce_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG           = "#0a0e14"   # site --bg-primary
AMBER        = "#d97706"   # ecommerce accent (CLAUDE.md #d97706 amber-orange)
GOLD         = "#f59e0b"   # secondary highlight
GREEN        = "#22c55e"
RED          = "#ef4444"
GREY         = "#64748b"   # site --text-muted
WHITE        = "#f1f5f9"   # site --text-primary
DIM          = "#94a3b8"   # site --text-secondary
CARD_BG      = "#1a2130"   # site --bg-card
PANEL_BORDER = "#2a3441"   # site --border-color

# ─── UNIVERSE ─────────────────────────────────────────────────────────────────

STOCKS = [
    ("AMZN", "Amazon"),
    ("SHOP", "Shopify"),
    ("EBAY", "eBay"),
    ("ETSY", "Etsy"),
    ("W",    "Wayfair"),
    ("CHWY", "Chewy"),
]

FRED_UMCSENT = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT"
FRED_RSXFS   = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RSXFS"

# ─── DATA FETCH ───────────────────────────────────────────────────────────────

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


def fetch_fred_series(url, n=18, retries=3):
    """Fetch last n monthly data points from a FRED CSV URL."""
    for i in range(retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "15", url],
                capture_output=True, text=True, check=True
            )
            reader = csv.reader(io.StringIO(result.stdout))
            rows = []
            for r in reader:
                if len(r) == 2 and r[0] not in ("DATE", "observation_date") and r[1].strip() not in (".", ""):
                    try:
                        rows.append((r[0], float(r[1])))
                    except ValueError:
                        pass
            if not rows:
                raise ValueError("no rows")
            return rows[-n:]
        except Exception:
            if i < retries - 1:
                time.sleep(5)
    return []


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(stock_data, sentiment_rows, retail_rows, spy_ret, vix):
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    # Top accent stripe
    fig.add_artist(plt.Line2D([0, 1], [0.993, 0.993],
                              transform=fig.transFigure, color=AMBER, linewidth=2.5,
                              solid_capstyle="butt", zorder=10))

    gs = gridspec.GridSpec(1, 3, figure=fig,
                           width_ratios=[4, 3.5, 2.5],
                           left=0.02, right=0.98,
                           top=GS_TOP, bottom=GS_BOTTOM, wspace=GS_WSPACE)
    ax_bars  = fig.add_subplot(gs[0, 0])
    ax_fred  = fig.add_subplot(gs[0, 1])
    ax_stats = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_fred, ax_stats]:
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values():
            sp.set_edgecolor(PANEL_BORDER)

    valid = [(sym, name, p, r) for (sym, name), (p, r) in zip(STOCKS, stock_data)
             if r is not None]
    valid_sorted = sorted(valid, key=lambda x: x[3])

    spy_r = spy_ret or 0
    sentiment_latest = sentiment_rows[-1][1] if sentiment_rows else None

    # Dynamic headline
    if valid_sorted:
        top = max(valid_sorted, key=lambda x: x[3])
        bot = min(valid_sorted, key=lambda x: x[3])
        avg = sum(x[3] for x in valid_sorted) / len(valid_sorted)
        if sentiment_latest and sentiment_latest < 60:
            headline = f"Consumer sentiment at {sentiment_latest:.1f} — ecommerce headwinds ahead"
        elif avg > spy_r + 2:
            headline = f"E-commerce outperforming — sector avg {avg:+.1f}% vs SPY {spy_r:+.1f}%"
        elif top[3] > 5:
            headline = f"{top[1]} leads e-commerce this week at {top[3]:+.1f}%"
        else:
            headline = f"{top[1]}: {top[3]:+.1f}%  |  {bot[1]}: {bot[3]:+.1f}%  |  SPY: {spy_r:+.1f}%"
    else:
        headline = "E-commerce sector — weekly snapshot"

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, HDR_TITLE_Y, f"E-Commerce Sector — {TODAY}",
             fontsize=FONT_TITLE, fontweight="bold", color=WHITE, va="top")
    fig.text(MARGIN_LEFT, HDR_HEADLINE_Y, headline, fontsize=FONT_HEADLINE, color=AMBER, va="top")
    vix_c = RED if (vix or 0) > 25 else (AMBER if (vix or 0) > 18 else WHITE)
    fig.text(MARGIN_RIGHT, HDR_STAT_Y,
             f"SPY: {spy_r:+.1f}%  |  VIX: {vix:.1f}" if vix else f"SPY: {spy_r:+.1f}%",
             fontsize=FONT_HEADLINE, color=vix_c, va="top", ha="right")
    fig.text(MARGIN_RIGHT, HDR_HANDLE_Y, "@Mboya_Jeffers",
             fontsize=FONT_HANDLE, color=AMBER, va="top", ha="right", fontweight="bold")

    # ── LEFT: BAR CHART ───────────────────────────────────────────────────────
    labels = [x[1] for x in valid_sorted]
    values = [x[3] for x in valid_sorted]
    bar_colors = [GREEN if v >= 0 else RED for v in values]

    y_pos = range(len(labels))
    ax_bars.barh(list(y_pos), values, color=bar_colors, height=0.65, alpha=0.85)
    ax_bars.set_yticks(list(y_pos))
    ax_bars.set_yticklabels(labels, fontsize=FONT_LABEL, color=WHITE)
    ax_bars.tick_params(axis="x", labelsize=FONT_TINY, colors=DIM)
    ax_bars.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
    ax_bars.set_title("5-Day Return (%)", fontsize=FONT_HEADLINE, color=DIM, pad=6)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
    ax_bars.grid(axis="x", color=PANEL_BORDER, linewidth=0.5, alpha=0.7)

    if values:
        xmin, xmax = min(values), max(values) if max(values) > 0 else 0.5
        buf = (xmax - xmin) * 0.28 or 1.0
        ax_bars.set_xlim(xmin - buf, xmax + buf)
        for i, (v, c) in enumerate(zip(values, bar_colors)):
            off = (xmax - xmin) * 0.04 or 0.1
            ha = "left" if v >= 0 else "right"
            ax_bars.text(v + (off if v >= 0 else -off), i, f"{v:+.2f}%",
                         va="center", ha=ha, fontsize=FONT_TINY, color=c)

    # ── CENTER: Consumer Sentiment + Retail Sales ──────────────────────────────
    ax_fred.axis("off")
    ax_fred.set_title("Consumer Sentiment (FRED UMCSENT)", fontsize=FONT_HEADLINE, color=DIM, pad=6)

    if sentiment_rows and len(sentiment_rows) >= 3:
        dates_s = [r[0][:7] for r in sentiment_rows]  # YYYY-MM
        vals_s  = [r[1] for r in sentiment_rows]
        xs = list(range(len(vals_s)))

        inner = ax_fred.inset_axes([0.05, 0.36, 0.90, 0.52])
        inner.set_facecolor("#160f00")
        for side in inner.spines.values():
            side.set_edgecolor(PANEL_BORDER)
        inner.tick_params(colors=GREY, labelsize=5.5)

        inner.plot(xs, vals_s, color=AMBER, linewidth=1.8, zorder=3)
        inner.fill_between(xs, min(vals_s) * 0.98, vals_s, alpha=0.15, color=AMBER)

        # Mark latest value
        inner.scatter([xs[-1]], [vals_s[-1]], color=GOLD, s=25, zorder=5)

        # Threshold lines
        inner.axhline(70, color=GREEN, linewidth=0.5, linestyle=":", alpha=0.6)
        inner.axhline(60, color=RED, linewidth=0.5, linestyle=":", alpha=0.6)

        # Only show first/last date labels
        tick_idx = [0, len(xs) - 1]
        inner.set_xticks(tick_idx)
        inner.set_xticklabels([dates_s[0], dates_s[-1]], fontsize=FONT_MICRO, color=GREY)
        inner.set_ylabel("Index", fontsize=FONT_MICRO, color=GREY)

        cur = vals_s[-1]
        prev = vals_s[-2] if len(vals_s) >= 2 else cur
        delta = cur - prev
        cur_c = GREEN if cur >= 70 else (AMBER if cur >= 60 else RED)

        ax_fred.text(0.50, 0.27, f"{cur:.1f}",
                     fontsize=FONT_TITLE, color=cur_c, fontweight="bold",
                     transform=ax_fred.transAxes, ha="center", va="bottom")
        ax_fred.text(0.50, 0.22, f"({delta:+.1f} vs prior month)",
                     fontsize=FONT_TINY, color=DIM,
                     transform=ax_fred.transAxes, ha="center", va="bottom")
        ax_fred.text(0.50, 0.16,
                     "Strong" if cur >= 80 else ("Fair" if cur >= 65 else ("Weak" if cur >= 55 else "Depressed")),
                     fontsize=FONT_HANDLE, color=cur_c, transform=ax_fred.transAxes,
                     ha="center", va="bottom", style="italic")
    else:
        ax_fred.text(0.5, 0.5, "Consumer sentiment\ndata unavailable",
                     fontsize=FONT_HEADLINE, color=GREY, transform=ax_fred.transAxes,
                     ha="center", va="center")

    # Retail sales note
    if retail_rows:
        rs_latest = retail_rows[-1][1]
        rs_prev   = retail_rows[-2][1] if len(retail_rows) >= 2 else rs_latest
        rs_mom    = (rs_latest - rs_prev) / rs_prev * 100
        rs_c = GREEN if rs_mom >= 0 else RED
        ax_fred.text(0.5, 0.09,
                     f"Retail sales: \\${rs_latest/1000:.1f}B  ({rs_mom:+.1f}% MoM)",
                     fontsize=FONT_LABEL, color=rs_c, transform=ax_fred.transAxes,
                     ha="center", va="bottom")

    ax_fred.text(0.5, 0.02, "FRED  |  Monthly  |  Univ. of Michigan",
                 fontsize=FONT_TINY, color=GREY, transform=ax_fred.transAxes,
                 ha="center", style="italic")

    # ── RIGHT: STATS ──────────────────────────────────────────────────────────
    ax_stats.axis("off")
    ax_stats.set_title("Sector Summary", fontsize=FONT_HEADLINE, color=DIM, pad=6)

    rows = []
    if valid_sorted:
        top2 = max(valid_sorted, key=lambda x: x[3])
        bot2 = min(valid_sorted, key=lambda x: x[3])
        avg2 = sum(x[3] for x in valid_sorted) / len(valid_sorted)
        rows.append(("Top Stock",       f"{top2[0]} {top2[3]:+.1f}%"))
        rows.append(("Worst Stock",     f"{bot2[0]} {bot2[3]:+.1f}%"))
        rows.append(("Sector Avg (5d)", f"{avg2:+.1f}%"))
    if spy_ret is not None:
        rows.append(("S&P 500 (5d)", f"{spy_r:+.1f}%"))
    if vix is not None:
        rows.append(("VIX", f"{vix:.1f}"))
    if sentiment_rows:
        rows.append(("Consumer Sentiment", f"{sentiment_rows[-1][1]:.1f}"))

    y2 = 0.85
    for label, val in rows:
        try:
            vc = GREEN if float(val.split(" ")[-1].replace("%", "")) >= 0 else RED
        except Exception:
            vc = WHITE
        ax_stats.text(0.06, y2, label, fontsize=FONT_LABEL, color=DIM,
                      transform=ax_stats.transAxes, va="top")
        ax_stats.text(0.94, y2, val, fontsize=FONT_HANDLE, color=vc, fontweight="bold",
                      transform=ax_stats.transAxes, ha="right", va="top")
        ax_stats.add_artist(plt.Line2D([0.03, 0.97], [y2 - 0.015, y2 - 0.015],
                                       transform=ax_stats.transAxes,
                                       color=PANEL_BORDER, linewidth=0.5))
        y2 -= 0.13

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, FOOTER_Y, f"Source: Yahoo Finance + FRED  |  Generated: {TIMESTAMP}",
             fontsize=FONT_SMALL, color=GREY, va="top")
    fig.text(MARGIN_RIGHT, FOOTER_Y, "@Mboya_Jeffers",
             fontsize=FONT_SMALL, color=AMBER, va="top", ha="right")
    fig.add_artist(plt.Line2D([MARGIN_LEFT, MARGIN_RIGHT], [FOOTER_LINE_Y, FOOTER_LINE_Y],
                              transform=fig.transFigure, color=PANEL_BORDER, linewidth=0.8))

    
    detect_and_fix_overlaps(fig)
    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching ecommerce stock data...")
    stock_data = []
    for sym, name in STOCKS:
        print(f"  {sym}...")
        p, r = fetch_5d(sym)
        stock_data.append((p, r))
        time.sleep(0.3)

    print("Fetching FRED consumer sentiment...")
    sentiment_rows = fetch_fred_series(FRED_UMCSENT, n=18)
    print(f"  Got {len(sentiment_rows)} sentiment data points")

    print("Fetching FRED retail sales...")
    retail_rows = fetch_fred_series(FRED_RSXFS, n=6)
    print(f"  Got {len(retail_rows)} retail sales data points")

    print("Fetching SPY + VIX...")
    _, spy_ret = fetch_5d("SPY")
    vix, _     = fetch_5d("^VIX")

    print("Drawing card...")
    draw_card(stock_data, sentiment_rows, retail_rows, spy_ret, vix)
    print("Done.")


if __name__ == "__main__":
    main()
