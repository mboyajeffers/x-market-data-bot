#!/usr/bin/env python3
"""
US Oil & Gas Snapshot — X card generator
Output: REVENUE/X/cards/oilgas_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #150800 background | #c2410c orange-red | white text
Data: FRED (WTI spot + Henry Hub NG) + yfinance (CL=F, NG=F, XLE, XOP, majors)
Note: EIA API v2 requires key — using FRED energy series (no key required).
"""

import csv
import io
import subprocess
import sys
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

OUT_DIR = Path(__file__).parent.parent / "cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY     = datetime.now().strftime("%Y-%m-%d")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"oilgas_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG      = "#150800"
ACCENT  = "#c2410c"
ORANGE  = "#ea580c"
GREEN   = "#22c55e"
RED     = "#ef4444"
GREY    = "#6b7280"
WHITE   = "#f1f5f9"
DIM     = "#94a3b8"
AMBER   = "#f59e0b"
CARD_BG = "#1e0d00"

# ─── ENERGY UNIVERSE ──────────────────────────────────────────────────────────

ENERGY_STOCKS = [
    ("XLE",  "Energy ETF"),
    ("XOP",  "Oil & Gas E&P"),
    ("CVX",  "Chevron"),
    ("XOM",  "Exxon Mobil"),
    ("COP",  "ConocoPhillips"),
    ("SLB",  "SLB"),
    ("MPC",  "Marathon Petrol."),
    ("PSX",  "Phillips 66"),
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def days_old(date_str):
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return 0

# ─── DATA FETCH ───────────────────────────────────────────────────────────────

def fetch_fred_series(series_id, start="2024-01-01", max_retries=3):
    """Returns (latest_val, latest_date, pct_chg_vs_prior)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "15", url],
                capture_output=True, text=True, timeout=20
            )
            if not result.stdout.strip():
                raise RuntimeError(f"Empty FRED response for {series_id}")
            reader = csv.reader(io.StringIO(result.stdout))
            next(reader)
            rows = [(r[0], float(r[1])) for r in reader
                    if len(r) >= 2 and r[1] and r[1] not in (".", "")]
            if len(rows) < 2:
                raise RuntimeError(f"FRED {series_id}: insufficient rows")
            latest_val, latest_date = rows[-1][1], rows[-1][0]
            prev_val = rows[-2][1]
            chg = (latest_val - prev_val) / prev_val * 100
            return latest_val, latest_date, chg
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(4)
                continue
            print(f"ERROR: FRED {series_id} failed: {e}")
            sys.exit(1)


def fetch_ticker_5d(ticker, max_retries=3):
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="10d")
            if hist.empty or len(hist) < 2:
                raise RuntimeError(f"{ticker}: insufficient history")
            closes = hist["Close"].dropna().tolist()
            ret_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else \
                     (closes[-1] - closes[0]) / closes[0] * 100
            return closes[-1], ret_5d
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            print(f"  WARNING: yfinance {ticker} failed: {e}")
            return None, None


def fetch_energy_equities():
    results = []
    for sym, name in ENERGY_STOCKS:
        price, ret5d = fetch_ticker_5d(sym)
        if price is not None:
            results.append({"ticker": sym, "name": name, "price": price, "ret5d": ret5d})
        time.sleep(0.25)
    return results


def fetch_fred_history(series_id, start="2025-01-01", max_retries=3):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "15", url],
                capture_output=True, text=True, timeout=20
            )
            reader = csv.reader(io.StringIO(result.stdout))
            next(reader)
            rows = [(r[0], float(r[1])) for r in reader
                    if len(r) >= 2 and r[1] and r[1] not in (".", "")]
            return rows
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(4)
                continue
            return []

# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(equity_data, wti_val, wti_date, wti_chg, ng_val, ng_date, ng_chg,
              wti_hist, ng_hist, cl_price, cl_ret5d, ng_price, ng_ret5d):

    spread = cl_price / (ng_price * 6) if ng_price > 0 else 0

    # Dynamic insight headline
    top = max(equity_data, key=lambda x: x["ret5d"]) if equity_data else None
    bot = min(equity_data, key=lambda x: x["ret5d"]) if equity_data else None
    if abs(cl_ret5d) > 4:
        direction = "surges" if cl_ret5d > 0 else "slides"
        headline = f"WTI {direction} {cl_ret5d:+.1f}% this week — energy sector responds"
    elif bot and bot["ret5d"] < -4:
        headline = f"{bot['name']} leads declines at {bot['ret5d']:.1f}% — sector under pressure"
    elif top and top["ret5d"] > 3:
        headline = f"{top['name']} outperforms at +{top['ret5d']:.1f}% — relative strength visible"
    elif spread > 25:
        headline = f"Oil/gas ratio elevated at {spread:.1f}x — energy commodity spread stretched"
    else:
        headline = f"WTI at \\${cl_price:.2f}/bbl  |  Henry Hub at \\${ng_val:.3f}/MMBtu  |  Ratio: {spread:.1f}x"

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    gs = gridspec.GridSpec(
        1, 3,
        figure=fig,
        width_ratios=[4.5, 2.5, 3],
        left=0.02, right=0.98,
        top=0.82, bottom=0.13,
        wspace=0.32,
    )

    ax_bars  = fig.add_subplot(gs[0, 0])
    ax_price = fig.add_subplot(gs[0, 1])
    ax_stats = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_price, ax_stats]:
        ax.set_facecolor(CARD_BG)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2a1200")

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.93, f"US Oil & Gas Weekly Snapshot — {TODAY}",
             fontsize=14, fontweight="bold", color=WHITE, va="top")
    fig.text(0.02, 0.88, headline,
             fontsize=9, color=ACCENT, va="top")
    cl_color = GREEN if cl_ret5d >= 0 else RED
    fig.text(
        0.98, 0.92,
        f"WTI Futures: \\${cl_price:.2f}  ({cl_ret5d:+.1f}% 5d)  |  "
        f"NG Futures: \\${ng_price:.3f}  ({ng_ret5d:+.1f}% 5d)",
        fontsize=8.5, color=cl_color, va="top", ha="right"
    )
    fig.text(0.98, 0.86, "@Mboya_Jeffers",
             fontsize=8.5, color=ACCENT, va="top", ha="right", fontweight="bold")

    # ── LEFT: EQUITY BAR CHART ────────────────────────────────────────────────
    sorted_eq = sorted(equity_data, key=lambda x: x["ret5d"])
    labels = [s["name"] for s in sorted_eq]
    values = [s["ret5d"] for s in sorted_eq]
    colors = [GREEN if v >= 0 else RED for v in values]

    y_pos = range(len(labels))
    ax_bars.barh(list(y_pos), values, color=colors, height=0.65, alpha=0.85)
    ax_bars.set_yticks(list(y_pos))
    ax_bars.set_yticklabels(labels, fontsize=7.5, color=WHITE)
    ax_bars.tick_params(axis="x", labelsize=7, colors=DIM)
    ax_bars.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
    ax_bars.set_title("5-Day Equity Return (%)", fontsize=9, color=DIM, pad=6)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
    ax_bars.grid(axis="x", color="#2a1200", linewidth=0.5, alpha=0.7)

    # Dynamic xlim — prevents label clipping
    xmin = min(values)
    xmax = max(values) if max(values) > 0 else 0.5
    buf  = (xmax - xmin) * 0.22
    ax_bars.set_xlim(xmin - buf, xmax + buf)
    offset = (xmax - xmin) * 0.03

    for i, (v, c) in enumerate(zip(values, colors)):
        ha = "left" if v >= 0 else "right"
        ax_bars.text(v + (offset if v >= 0 else -offset), i,
                     f"{v:+.2f}%", va="center", ha=ha, fontsize=6.5, color=c)

    # ── CENTER: WTI + NG SPARKLINES ───────────────────────────────────────────
    ax_price.axis("off")
    ax_price.set_title("Spot Prices (FRED)", fontsize=9, color=DIM, pad=6)

    if wti_hist:
        wti_vals = [v for _, v in wti_hist[-30:]]
        ax_wti = ax_price.inset_axes([0.05, 0.62, 0.90, 0.28])
        ax_wti.set_facecolor("#150800")
        wti_color = GREEN if wti_vals[-1] >= wti_vals[0] else RED
        ax_wti.plot(range(len(wti_vals)), wti_vals, color=wti_color, linewidth=1.5)
        ax_wti.fill_between(range(len(wti_vals)), wti_vals,
                            min(wti_vals) * 0.995, alpha=0.2, color=wti_color)
        ax_wti.set_xticks([])
        ax_wti.set_yticks([min(wti_vals), max(wti_vals)])
        ax_wti.tick_params(axis="y", labelsize=6, colors=DIM)
        for spine in ax_wti.spines.values():
            spine.set_edgecolor("#2a1200")

    ax_price.text(0.5, 0.93, "WTI Crude Spot", fontsize=8, color=DIM,
                  transform=ax_price.transAxes, ha="center")
    wti_color_disp = GREEN if wti_chg >= 0 else RED
    ax_price.text(0.5, 0.56, f"\\${wti_val:.2f}/bbl  {wti_chg:+.1f}%",
                  fontsize=9, color=wti_color_disp, fontweight="bold",
                  transform=ax_price.transAxes, ha="center")
    # Staleness: FRED WTI is daily but may lag 1-3 days
    wti_age = days_old(wti_date)
    wti_date_color = AMBER if wti_age > 7 else GREY
    ax_price.text(0.5, 0.50, f"as of {wti_date}" + (" ⚠" if wti_age > 7 else ""),
                  fontsize=6.5, color=wti_date_color,
                  transform=ax_price.transAxes, ha="center")

    ax_price.add_artist(plt.Line2D([0.05, 0.95], [0.45, 0.45],
                                    transform=ax_price.transAxes,
                                    color="#2a1200", linewidth=1))

    if ng_hist:
        ng_vals = [v for _, v in ng_hist[-30:]]
        ax_ng = ax_price.inset_axes([0.05, 0.14, 0.90, 0.28])
        ax_ng.set_facecolor("#150800")
        ng_c = GREEN if ng_vals[-1] >= ng_vals[0] else RED
        ax_ng.plot(range(len(ng_vals)), ng_vals, color=ng_c, linewidth=1.5)
        ax_ng.fill_between(range(len(ng_vals)), ng_vals,
                           min(ng_vals) * 0.995, alpha=0.2, color=ng_c)
        ax_ng.set_xticks([])
        ax_ng.set_yticks([min(ng_vals), max(ng_vals)])
        ax_ng.tick_params(axis="y", labelsize=6, colors=DIM)
        for spine in ax_ng.spines.values():
            spine.set_edgecolor("#2a1200")

    ax_price.text(0.5, 0.45, "Henry Hub Nat Gas", fontsize=8, color=DIM,
                  transform=ax_price.transAxes, ha="center")
    ng_color_disp = GREEN if ng_chg >= 0 else RED
    ax_price.text(0.5, 0.09, f"\\${ng_val:.3f}/MMBtu  {ng_chg:+.1f}%",
                  fontsize=9, color=ng_color_disp, fontweight="bold",
                  transform=ax_price.transAxes, ha="center")
    # Staleness: FRED MHHNGSP is weekly — amber if >14 days
    ng_age = days_old(ng_date)
    ng_date_color = AMBER if ng_age > 14 else GREY
    ax_price.text(0.5, 0.03, f"as of {ng_date}" + (" ⚠ lag" if ng_age > 14 else ""),
                  fontsize=6.5, color=ng_date_color,
                  transform=ax_price.transAxes, ha="center")

    # ── RIGHT: MARKET STATS ────────────────────────────────────────────────────
    ax_stats.axis("off")
    ax_stats.set_title("Market Snapshot", fontsize=9, color=DIM, pad=6)

    xle_ret = next((e["ret5d"] for e in equity_data if e["ticker"] == "XLE"), 0.0)
    xop_ret = next((e["ret5d"] for e in equity_data if e["ticker"] == "XOP"), 0.0)

    stats = [
        ("WTI Futures (CL=F)",    f"\\${cl_price:.2f}"),
        ("WTI 5-Day Return",      f"{cl_ret5d:+.2f}%"),
        ("Nat Gas Futures (NG=F)", f"\\${ng_price:.3f}"),
        ("NG 5-Day Return",       f"{ng_ret5d:+.2f}%"),
        ("XLE 5-Day",             f"{xle_ret:+.2f}%"),
        ("XOP 5-Day",             f"{xop_ret:+.2f}%"),
    ]

    row_h2 = 0.125
    y2 = 0.86
    for label, val in stats:
        val_color = WHITE
        if "Return" in label or "5-Day" in label:
            try:
                num = float(val.replace("%", "").replace("+", ""))
                val_color = GREEN if num >= 0 else RED
            except ValueError:
                pass
        ax_stats.text(0.06, y2, label, fontsize=8, color=DIM,
                      transform=ax_stats.transAxes, va="top")
        ax_stats.text(0.94, y2, val, fontsize=8.5, color=val_color,
                      fontweight="bold", transform=ax_stats.transAxes,
                      ha="right", va="top")
        ax_stats.add_artist(plt.Line2D(
            [0.03, 0.97], [y2 - 0.015, y2 - 0.015],
            transform=ax_stats.transAxes, color="#2a1200", linewidth=0.5,
        ))
        y2 -= row_h2

    # Oil/gas spread box
    y2 -= 0.04
    rect = FancyBboxPatch((0.03, y2 - 0.05), 0.94, 0.17,
                          boxstyle="round,pad=0.02",
                          facecolor="#1e0d00", edgecolor=ACCENT, linewidth=1,
                          transform=ax_stats.transAxes, clip_on=False)
    ax_stats.add_patch(rect)
    ax_stats.text(0.5, y2 + 0.04, f"Oil/Gas Ratio (BTU): {spread:.1f}x",
                  fontsize=9, color=ACCENT, fontweight="bold",
                  transform=ax_stats.transAxes, ha="center", va="center")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.06,
             f"Source: FRED (DCOILWTICO, MHHNGSP) + Yahoo Finance (NYMEX)  |  Generated: {TIMESTAMP}",
             fontsize=7.5, color=GREY, va="top")
    fig.text(0.98, 0.06, "github.com/mboyajeffers/data-intelligence-platform",
             fontsize=7.5, color=ACCENT, va="top", ha="right")

    fig.add_artist(plt.Line2D([0.02, 0.98], [0.105, 0.105],
                              transform=fig.transFigure,
                              color="#2a1200", linewidth=0.8))

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching FRED: WTI Crude Spot (DCOILWTICO)...")
    wti_val, wti_date, wti_chg = fetch_fred_series("DCOILWTICO", start="2025-01-01")
    print(f"  WTI: ${wti_val:.2f} as of {wti_date} ({wti_chg:+.1f}% vs prior)")

    print("Fetching FRED: Henry Hub Nat Gas Spot (MHHNGSP)...")
    ng_val, ng_date, ng_chg = fetch_fred_series("MHHNGSP", start="2025-01-01")
    print(f"  Henry Hub: ${ng_val:.3f} as of {ng_date} ({ng_chg:+.1f}% vs prior)")

    print("Fetching WTI price history for sparkline...")
    wti_hist = fetch_fred_history("DCOILWTICO", start="2025-01-01")

    print("Fetching NG price history for sparkline...")
    ng_hist = fetch_fred_history("MHHNGSP", start="2025-01-01")

    print("Fetching WTI futures (CL=F)...")
    cl_price, cl_ret5d = fetch_ticker_5d("CL=F")
    cl_price  = cl_price  or wti_val
    cl_ret5d  = cl_ret5d  or 0.0
    print(f"  CL=F: ${cl_price:.2f}  5d: {cl_ret5d:+.1f}%")

    print("Fetching NG futures (NG=F)...")
    ng_fut_price, ng_ret5d = fetch_ticker_5d("NG=F")
    ng_fut_price = ng_fut_price or ng_val
    ng_ret5d     = ng_ret5d     or 0.0
    print(f"  NG=F: ${ng_fut_price:.3f}  5d: {ng_ret5d:+.1f}%")

    print("Fetching energy equity returns...")
    equity_data = fetch_energy_equities()

    print("Drawing card...")
    draw_card(
        equity_data,
        wti_val, wti_date, wti_chg,
        ng_val, ng_date, ng_chg,
        wti_hist, ng_hist,
        cl_price, cl_ret5d,
        ng_fut_price, ng_ret5d
    )
    print("Done.")


if __name__ == "__main__":
    main()
