#!/usr/bin/env python3
"""
Market Snapshot — X card generator (Finance / Equity)
Output: REVENUE/X/cards/finance_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #0a1628 background | #2d9596 teal | white text
Data: yfinance (sector ETFs + SPY + VIX) + FRED (Fed Funds, CPI, 10Y)
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
OUT_PATH  = OUT_DIR / f"finance_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG      = "#0a1628"
TEAL    = "#2d9596"
GREEN   = "#22c55e"
RED     = "#ef4444"
GREY    = "#6b7280"
WHITE   = "#f1f5f9"
DIM     = "#94a3b8"
AMBER   = "#f59e0b"
CARD_BG = "#0f1f38"

# ─── SECTORS ──────────────────────────────────────────────────────────────────

SECTORS = [
    ("XLK",  "Technology"),
    ("XLF",  "Financials"),
    ("XLE",  "Energy"),
    ("XLV",  "Health Care"),
    ("XLY",  "Cons. Discret."),
    ("XLP",  "Cons. Staples"),
    ("XLI",  "Industrials"),
    ("XLB",  "Materials"),
    ("XLRE", "Real Estate"),
    ("XLU",  "Utilities"),
    ("XLC",  "Comm. Services"),
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def days_old(date_str):
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return 0

# ─── DATA FETCH ───────────────────────────────────────────────────────────────

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
            print(f"ERROR: yfinance {ticker} failed: {e}")
            sys.exit(1)


def fetch_spy_ytd(max_retries=3):
    for attempt in range(max_retries):
        try:
            t = yf.Ticker("SPY")
            hist = t.history(start=f"{datetime.now().year}-01-02")
            if hist.empty:
                raise RuntimeError("SPY YTD: empty")
            closes = hist["Close"].dropna().tolist()
            ytd = (closes[-1] - closes[0]) / closes[0] * 100
            return closes[-1], ytd
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            print(f"ERROR: SPY YTD failed: {e}")
            sys.exit(1)


def fetch_vix(max_retries=3):
    for attempt in range(max_retries):
        try:
            t = yf.Ticker("^VIX")
            hist = t.history(period="5d")
            if hist.empty:
                raise RuntimeError("VIX: empty")
            return hist["Close"].dropna().tolist()[-1]
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            print(f"ERROR: VIX failed: {e}")
            sys.exit(1)


def fetch_fred_latest(series_id, start="2024-01-01", max_retries=3):
    """Returns (value, date_str)."""
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
            if not rows:
                raise RuntimeError(f"FRED: no valid rows for {series_id}")
            return rows[-1][1], rows[-1][0]
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(4)
                continue
            print(f"ERROR: FRED {series_id} failed: {e}")
            sys.exit(1)


def fetch_cpi_yoy(max_retries=3):
    """Returns (yoy_pct, date_str)."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL&cosd=2024-01-01"
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
            if len(rows) < 13:
                raise RuntimeError("FRED CPIAUCSL: < 13 rows")
            yoy = (rows[-1][1] / rows[-13][1] - 1) * 100
            return round(yoy, 1), rows[-1][0]
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(4)
                continue
            print(f"ERROR: CPI YoY failed: {e}")
            sys.exit(1)

# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(sector_data, spy_price, spy_ytd, vix, fed_funds, cpi_yoy, ten_yr,
              fed_date, cpi_date, ten_yr_date):

    # Dynamic insight headline
    top = max(sector_data, key=lambda x: x["ret5d"])
    bot = min(sector_data, key=lambda x: x["ret5d"])
    spread = top["ret5d"] - bot["ret5d"]
    if vix > 28:
        headline = f"Volatility spike: VIX at {vix:.1f} — risk-off conditions"
    elif bot["ret5d"] < -4:
        headline = f"{bot['name']} leads declines — down {bot['ret5d']:.1f}% this week"
    elif top["ret5d"] > 4:
        headline = f"{top['name']} leads sectors — up +{top['ret5d']:.1f}% this week"
    elif spread > 7:
        headline = f"Wide sector spread: {top['name']} +{top['ret5d']:.1f}% vs {bot['name']} {bot['ret5d']:.1f}%"
    elif spy_ytd > 18:
        headline = f"SPY up {spy_ytd:.1f}% YTD — bull trend intact  |  VIX: {vix:.1f}"
    elif spy_ytd < -12:
        headline = f"Correction territory: SPY down {abs(spy_ytd):.1f}% YTD"
    else:
        headline = f"Mixed week: {top['name']} leads +{top['ret5d']:.1f}%  |  {bot['name']} lags {bot['ret5d']:.1f}%"

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    gs = gridspec.GridSpec(
        1, 3,
        figure=fig,
        width_ratios=[4.5, 3, 2.5],
        left=0.02, right=0.98,
        top=0.82, bottom=0.13,
        wspace=0.32,
    )

    ax_sectors = fig.add_subplot(gs[0, 0])
    ax_macro   = fig.add_subplot(gs[0, 1])
    ax_movers  = fig.add_subplot(gs[0, 2])

    for ax in [ax_sectors, ax_macro, ax_movers]:
        ax.set_facecolor(CARD_BG)
        for spine in ax.spines.values():
            spine.set_edgecolor("#1a2f4a")

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.93, f"Market Snapshot — {TODAY}",
             fontsize=14, fontweight="bold", color=WHITE, va="top")
    fig.text(0.02, 0.88, headline,
             fontsize=9, color=TEAL, va="top")
    fig.text(0.98, 0.92, f"SPY: ${spy_price:.2f}  |  YTD: {spy_ytd:+.1f}%  |  VIX: {vix:.1f}",
             fontsize=9, color=TEAL, va="top", ha="right")
    fig.text(0.98, 0.86, "@Mboya_Jeffers",
             fontsize=8.5, color=TEAL, va="top", ha="right", fontweight="bold")

    # ── LEFT: SECTOR BAR CHART ────────────────────────────────────────────────
    sorted_sectors = sorted(sector_data, key=lambda x: x["ret5d"])
    labels = [s["name"] for s in sorted_sectors]
    values = [s["ret5d"] for s in sorted_sectors]
    colors = [GREEN if v >= 0 else RED for v in values]

    y_pos = range(len(labels))
    ax_sectors.barh(list(y_pos), values, color=colors, height=0.65, alpha=0.85)
    ax_sectors.set_yticks(list(y_pos))
    ax_sectors.set_yticklabels(labels, fontsize=7.5, color=WHITE)
    ax_sectors.tick_params(axis="x", labelsize=7, colors=DIM)
    ax_sectors.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
    ax_sectors.set_title("5-Day Sector Return (%)", fontsize=9, color=DIM, pad=6)
    ax_sectors.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
    ax_sectors.grid(axis="x", color="#1a2f4a", linewidth=0.5, alpha=0.7)

    # Dynamic xlim — prevents label clipping on extreme values
    xmin = min(values)
    xmax = max(values) if max(values) > 0 else 0.5
    buf  = (xmax - xmin) * 0.22
    ax_sectors.set_xlim(xmin - buf, xmax + buf)
    offset = (xmax - xmin) * 0.03

    for i, (v, c) in enumerate(zip(values, colors)):
        ha = "left" if v >= 0 else "right"
        ax_sectors.text(v + (offset if v >= 0 else -offset), i,
                        f"{v:+.2f}%", va="center", ha=ha, fontsize=6.5, color=c)

    # ── CENTER: MACRO TABLE ────────────────────────────────────────────────────
    ax_macro.axis("off")
    ax_macro.set_title("Macro Indicators", fontsize=9, color=DIM, pad=6)

    macro_rows = [
        ("Fed Funds Rate", f"{fed_funds:.2f}%"),
        ("CPI YoY",        f"{cpi_yoy:+.1f}%"),
        ("10Y Treasury",   f"{ten_yr:.2f}%"),
        ("SPY YTD",        f"{spy_ytd:+.1f}%"),
        ("VIX",            f"{vix:.1f}"),
    ]

    row_h = 0.145
    y = 0.85
    for i, (label, val) in enumerate(macro_rows):
        bg = "#0a1628" if i % 2 == 0 else CARD_BG
        rect = FancyBboxPatch((0.01, y - 0.01), 0.98, row_h,
                              boxstyle="round,pad=0.01",
                              facecolor=bg, edgecolor="none",
                              transform=ax_macro.transAxes, clip_on=False)
        ax_macro.add_patch(rect)
        ax_macro.text(0.06, y + 0.05, label, fontsize=8.5, color=DIM,
                      transform=ax_macro.transAxes, va="center")

        val_color = WHITE
        try:
            num = float(val.replace("%", "").replace("+", "").replace("$", ""))
            if label == "VIX":
                val_color = RED if num > 25 else (WHITE if num > 18 else GREEN)
            elif label == "SPY YTD":
                val_color = GREEN if num > 0 else RED
            elif label == "CPI YoY":
                val_color = RED if num > 4 else (WHITE if num > 2.5 else GREEN)
        except ValueError:
            pass

        ax_macro.text(0.94, y + 0.05, val, fontsize=9, color=val_color,
                      fontweight="bold", transform=ax_macro.transAxes,
                      ha="right", va="center")
        y -= row_h

    # FRED data date — amber if monthly data is stale (>35 days)
    stale = days_old(cpi_date) > 35 or days_old(fed_date) > 35
    stale_color = AMBER if stale else GREY
    fred_note = f"FRED data as of {cpi_date}" + ("  ⚠ publication lag" if stale else "")
    ax_macro.text(0.5, 0.02, fred_note, fontsize=6, color=stale_color,
                  transform=ax_macro.transAxes, ha="center", style="italic")

    # ── RIGHT: TOP & BOTTOM MOVERS ────────────────────────────────────────────
    ax_movers.axis("off")
    ax_movers.set_title("Week Movers", fontsize=9, color=DIM, pad=6)

    top2    = sorted(sector_data, key=lambda x: x["ret5d"], reverse=True)[:2]
    bottom2 = sorted(sector_data, key=lambda x: x["ret5d"])[:2]

    ax_movers.text(0.5, 0.91, "TOP", fontsize=8, color=GREEN, fontweight="bold",
                   transform=ax_movers.transAxes, ha="center")
    for i, (s, yb) in enumerate(zip(top2, [0.82, 0.62])):
        ax_movers.text(0.5, yb,        s["ticker"],                fontsize=10, color=GREEN,
                       fontweight="bold", transform=ax_movers.transAxes, ha="center")
        ax_movers.text(0.5, yb - 0.05, s["name"],                  fontsize=6.5, color=DIM,
                       transform=ax_movers.transAxes, ha="center")
        arrow = "▲" if s["ret5d"] > 0 else "▼"
        ax_movers.text(0.5, yb - 0.11, f"{arrow} {s['ret5d']:+.2f}%", fontsize=9,
                       color=GREEN, fontweight="bold", transform=ax_movers.transAxes, ha="center")

    ax_movers.add_artist(plt.Line2D(
        [0.05, 0.95], [0.44, 0.44],
        transform=ax_movers.transAxes, color="#1a2f4a", linewidth=1))

    ax_movers.text(0.5, 0.40, "BOTTOM", fontsize=8, color=RED, fontweight="bold",
                   transform=ax_movers.transAxes, ha="center")
    for i, (s, yb) in enumerate(zip(bottom2, [0.30, 0.12])):
        ax_movers.text(0.5, yb,        s["ticker"],                fontsize=10, color=RED,
                       fontweight="bold", transform=ax_movers.transAxes, ha="center")
        ax_movers.text(0.5, yb - 0.05, s["name"],                  fontsize=6.5, color=DIM,
                       transform=ax_movers.transAxes, ha="center")
        arrow = "▲" if s["ret5d"] > 0 else "▼"
        ax_movers.text(0.5, yb - 0.11, f"{arrow} {s['ret5d']:+.2f}%", fontsize=9,
                       color=RED, fontweight="bold", transform=ax_movers.transAxes, ha="center")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.06, f"Source: Yahoo Finance + FRED  |  Generated: {TIMESTAMP}",
             fontsize=7.5, color=GREY, va="top")
    fig.text(0.98, 0.06, "github.com/mboyajeffers/data-intelligence-platform",
             fontsize=7.5, color=TEAL, va="top", ha="right")

    fig.add_artist(plt.Line2D([0.02, 0.98], [0.105, 0.105],
                              transform=fig.transFigure,
                              color="#1a2f4a", linewidth=0.8))

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching sector ETF data (5d returns)...")
    sector_data = []
    for ticker, name in SECTORS:
        price, ret5d = fetch_ticker_5d(ticker)
        sector_data.append({"ticker": ticker, "name": name, "price": price, "ret5d": ret5d})
        time.sleep(0.3)

    print("Fetching SPY YTD...")
    spy_price, spy_ytd = fetch_spy_ytd()

    print("Fetching VIX...")
    vix = fetch_vix()

    print("Fetching FRED: Fed Funds Rate...")
    fed_funds, fed_date = fetch_fred_latest("FEDFUNDS", start="2024-01-01")

    print("Fetching FRED: CPI YoY...")
    cpi_yoy, cpi_date = fetch_cpi_yoy()

    print("Fetching FRED: 10Y Treasury yield...")
    ten_yr, ten_yr_date = fetch_fred_latest("DGS10", start="2025-01-01")

    print("Drawing card...")
    draw_card(sector_data, spy_price, spy_ytd, vix, fed_funds, cpi_yoy, ten_yr,
              fed_date, cpi_date, ten_yr_date)
    print("Done.")


if __name__ == "__main__":
    main()
