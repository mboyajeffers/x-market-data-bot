#!/usr/bin/env python3
"""
Media & Streaming Sector Snapshot — X card generator
Output: REVENUE/X/cards/media_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #06091a background | #2563eb blue
Data: yfinance (streaming/media stocks + XLC comm. services ETF + SPY/VIX)
"""

import time
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import yfinance as yf

# ─── PATHS ────────────────────────────────────────────────────────────────────

OUT_DIR   = Path("/Users/mboyajeffers/Claude_Projects/REVENUE/X/cards")
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY     = datetime.now().strftime("%Y-%m-%d")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"media_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG        = "#06091a"
BLUE      = "#2563eb"
LIGHT_BLU = "#60a5fa"
GREEN     = "#22c55e"
RED       = "#ef4444"
AMBER     = "#f59e0b"
GREY      = "#6b7280"
WHITE     = "#f1f5f9"
DIM       = "#94a3b8"
CARD_BG   = "#0a0f2a"

# ─── UNIVERSE ─────────────────────────────────────────────────────────────────

STOCKS = [
    ("NFLX", "Netflix"),
    ("DIS",  "Disney"),
    ("WBD",  "Warner Bros. Discovery"),
    ("FOXA", "Fox Corporation"),
    ("SPOT", "Spotify"),
    ("ROKU", "Roku"),
]

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


def fetch_30d(ticker, retries=3):
    for i in range(retries):
        try:
            h = yf.Ticker(ticker).history(period="35d")
            if h.empty or len(h) < 5:
                raise ValueError("insufficient data")
            return h["Close"].dropna().tolist()
        except Exception:
            if i < retries - 1:
                time.sleep(2)
    return []


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(stock_data, xlc_prices, spy_prices, spy_ret, vix):
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)
    gs = gridspec.GridSpec(1, 3, figure=fig,
                           width_ratios=[4, 3.5, 2.5],
                           left=0.02, right=0.98,
                           top=0.82, bottom=0.13, wspace=0.33)
    ax_bars  = fig.add_subplot(gs[0, 0])
    ax_spark = fig.add_subplot(gs[0, 1])
    ax_stats = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_spark, ax_stats]:
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values():
            sp.set_edgecolor("#0f1840")

    valid = [(sym, name, p, r) for (sym, name), (p, r) in zip(STOCKS, stock_data)
             if r is not None]
    valid_sorted = sorted(valid, key=lambda x: x[3])

    spy_r = spy_ret or 0
    if valid_sorted:
        top = max(valid_sorted, key=lambda x: x[3])
        bot = min(valid_sorted, key=lambda x: x[3])
        avg = sum(x[3] for x in valid_sorted) / len(valid_sorted)
        if avg > spy_r + 2:
            headline = f"Media/streaming beating market — sector avg {avg:+.1f}% vs SPY {spy_r:+.1f}%"
        elif avg < spy_r - 2:
            headline = f"Media sector lagging — avg {avg:+.1f}% vs SPY {spy_r:+.1f}%"
        elif top[3] > 5:
            headline = f"{top[1]} leads media this week at {top[3]:+.1f}%"
        else:
            headline = f"{top[1]}: {top[3]:+.1f}%  |  {bot[1]}: {bot[3]:+.1f}%  |  SPY: {spy_r:+.1f}%"
    else:
        headline = "Media & streaming sector — weekly snapshot"

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.93, f"Media & Streaming Sector — {TODAY}",
             fontsize=14, fontweight="bold", color=WHITE, va="top")
    fig.text(0.02, 0.88, headline, fontsize=9, color=LIGHT_BLU, va="top")
    vix_c = RED if (vix or 0) > 25 else (AMBER if (vix or 0) > 18 else WHITE)
    fig.text(0.98, 0.92,
             f"SPY: {spy_r:+.1f}%  |  VIX: {vix:.1f}" if vix else f"SPY: {spy_r:+.1f}%",
             fontsize=9, color=vix_c, va="top", ha="right")
    fig.text(0.98, 0.86, "@Mboya_Jeffers",
             fontsize=8.5, color=LIGHT_BLU, va="top", ha="right", fontweight="bold")

    # ── LEFT: BAR CHART ───────────────────────────────────────────────────────
    labels = [x[1] for x in valid_sorted]
    values = [x[3] for x in valid_sorted]
    bar_colors = [GREEN if v >= 0 else RED for v in values]

    y_pos = range(len(labels))
    ax_bars.barh(list(y_pos), values, color=bar_colors, height=0.65, alpha=0.85)
    ax_bars.set_yticks(list(y_pos))
    ax_bars.set_yticklabels(labels, fontsize=7.5, color=WHITE)
    ax_bars.tick_params(axis="x", labelsize=7, colors=DIM)
    ax_bars.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
    ax_bars.set_title("5-Day Return (%)", fontsize=9, color=DIM, pad=6)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
    ax_bars.grid(axis="x", color="#0f1840", linewidth=0.5, alpha=0.7)

    if values:
        xmin, xmax = min(values), max(values) if max(values) > 0 else 0.5
        buf = (xmax - xmin) * 0.28 or 1.0
        ax_bars.set_xlim(xmin - buf, xmax + buf)
        for i, (v, c) in enumerate(zip(values, bar_colors)):
            off = (xmax - xmin) * 0.04 or 0.1
            ha = "left" if v >= 0 else "right"
            ax_bars.text(v + (off if v >= 0 else -off), i, f"{v:+.2f}%",
                         va="center", ha=ha, fontsize=7, color=c)

    # ── CENTER: XLC vs SPY 30d sparklines ─────────────────────────────────────
    ax_spark.axis("off")
    ax_spark.set_title("XLC Comm. Services ETF vs S&P 500 — 30 days", fontsize=9, color=DIM, pad=6)

    if xlc_prices and spy_prices and len(xlc_prices) >= 5 and len(spy_prices) >= 5:
        n = min(len(xlc_prices), len(spy_prices))
        xp = xlc_prices[-n:]; sp2 = spy_prices[-n:]
        xn = [p / xp[0] * 100 for p in xp]
        sn = [p / sp2[0] * 100 for p in sp2]
        xs = list(range(len(xn)))

        inner = ax_spark.inset_axes([0.05, 0.20, 0.90, 0.68])
        inner.set_facecolor("#050814")
        for side in inner.spines.values():
            side.set_edgecolor("#0f1840")
        inner.tick_params(colors=GREY, labelsize=5.5)

        inner.plot(xs, xn, color=BLUE, linewidth=1.8, label="XLC", zorder=3)
        inner.fill_between(xs, 100, xn, alpha=0.12, color=BLUE)
        inner.plot(xs, sn, color=AMBER, linewidth=1, linestyle="--", label="SPY", alpha=0.65, zorder=2)
        inner.axhline(100, color=GREY, linewidth=0.5, linestyle=":")
        inner.set_xlabel("30 trading days", fontsize=5.5, color=GREY)
        inner.legend(fontsize=6.5, loc="upper left", framealpha=0.2)

        xd = xn[-1] - 100; sd = sn[-1] - 100
        ax_spark.text(0.06, 0.10, f"XLC: {xd:+.1f}%",
                      fontsize=8.5, color=BLUE if xd >= 0 else RED,
                      transform=ax_spark.transAxes, va="bottom", fontweight="bold")
        ax_spark.text(0.55, 0.10, f"SPY: {sd:+.1f}%",
                      fontsize=8.5, color=AMBER if sd >= 0 else RED,
                      transform=ax_spark.transAxes, va="bottom")
    else:
        ax_spark.text(0.5, 0.5, "Sparkline data\nunavailable",
                      fontsize=9, color=GREY, transform=ax_spark.transAxes,
                      ha="center", va="center")

    ax_spark.text(0.5, 0.02, "Normalized: 100 = 30 days ago  |  Yahoo Finance",
                  fontsize=6, color=GREY, transform=ax_spark.transAxes,
                  ha="center", style="italic")

    # ── RIGHT: STATS ──────────────────────────────────────────────────────────
    ax_stats.axis("off")
    ax_stats.set_title("Sector Summary", fontsize=9, color=DIM, pad=6)

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
    if xlc_prices and len(xlc_prices) >= 6:
        xlc5d = (xlc_prices[-1] / xlc_prices[-6] - 1) * 100
        rows.append(("XLC ETF (5d)", f"{xlc5d:+.1f}%"))

    y2 = 0.85
    for label, val in rows:
        try:
            vc = GREEN if float(val.split(" ")[-1].replace("%", "")) >= 0 else RED
        except Exception:
            vc = WHITE
        ax_stats.text(0.06, y2, label, fontsize=7.5, color=DIM,
                      transform=ax_stats.transAxes, va="top")
        ax_stats.text(0.94, y2, val, fontsize=8.5, color=vc, fontweight="bold",
                      transform=ax_stats.transAxes, ha="right", va="top")
        ax_stats.add_artist(plt.Line2D([0.03, 0.97], [y2 - 0.015, y2 - 0.015],
                                       transform=ax_stats.transAxes,
                                       color="#0f1840", linewidth=0.5))
        y2 -= 0.13

    y2 -= 0.03
    rect = FancyBboxPatch((0.03, y2 - 0.08), 0.94, 0.15,
                          boxstyle="round,pad=0.02",
                          facecolor="#050814", edgecolor=BLUE, linewidth=0.8,
                          transform=ax_stats.transAxes, clip_on=False)
    ax_stats.add_patch(rect)
    ax_stats.text(0.5, y2, "Streaming · Linear TV · Podcasts · Film",
                  fontsize=6.5, color=LIGHT_BLU, transform=ax_stats.transAxes,
                  ha="center", va="center", style="italic")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.06, f"Source: Yahoo Finance  |  Generated: {TIMESTAMP}",
             fontsize=7.5, color=GREY, va="top")
    fig.text(0.98, 0.06, "github.com/mboyajeffers/data-intelligence-platform",
             fontsize=7.5, color=LIGHT_BLU, va="top", ha="right")
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.105, 0.105],
                              transform=fig.transFigure, color="#0f1840", linewidth=0.8))

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching media/streaming stock data...")
    stock_data = []
    for sym, name in STOCKS:
        print(f"  {sym}...")
        p, r = fetch_5d(sym)
        stock_data.append((p, r))
        time.sleep(0.3)

    print("Fetching XLC + SPY + VIX...")
    xlc_prices = fetch_30d("XLC")
    spy_prices  = fetch_30d("SPY")
    _, spy_ret  = fetch_5d("SPY")
    vix, _      = fetch_5d("^VIX")

    print("Drawing card...")
    draw_card(stock_data, xlc_prices, spy_prices, spy_ret, vix)
    print("Done.")


if __name__ == "__main__":
    main()
