#!/usr/bin/env python3
"""
Sports Betting Sector — X Card Generator
Renderer: HTML/CSS + SVG → Chrome Headless → PNG

Layout: 3 columns — bar chart | SVG sparkline | sector stats
Output: REVENUE/X/cards/betting_x_card_YYYY-MM-DD.png (1200×675)
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from jinja2 import Environment, FileSystemLoader

from render_card import render_html_to_png, quality_check

sys.path.insert(0, str(Path(__file__).parent.parent / "bot"))
try:
    from affiliate_config import CONTRA_BETTING_URL, BIO_LINK as _BIO_LINK
    _contra_betting_live = not CONTRA_BETTING_URL.startswith("[")
    _CTA_LINK  = CONTRA_BETTING_URL if _contra_betting_live else _BIO_LINK
    _CTA_LABEL = "Monthly operator intelligence" if _contra_betting_live else "Best sportsbook promos"
except ImportError:
    _CTA_LINK  = "beacons.ai/mboyajeffers"
    _CTA_LABEL = "Best sportsbook promos"

# ─── PATHS ────────────────────────────────────────────────────────────────────

SCRIPTS_DIR   = Path(__file__).parent
TEMPLATES_DIR = SCRIPTS_DIR.parent / "templates"
OUT_DIR       = SCRIPTS_DIR.parent / "cards"
SCRATCHPAD    = Path("/private/tmp/claude-501/-Users-mboyajeffers/65dd444d-a640-4403-88ca-79db6fc25738/scratchpad")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SCRATCHPAD.mkdir(parents=True, exist_ok=True)

_now_utc  = datetime.now(timezone.utc)
TODAY     = _now_utc.strftime("%Y-%m-%d")
TIMESTAMP = _now_utc.strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"betting_x_card_{TODAY}.png"

# ─── HANDLE COMPOSITION (AGA) ─────────────────────────────────────────────────

LIVE_BETTING_PCT = 62   # live/in-play as % of handle (AGA 2025-2026)
PARLAY_PCT       = 27   # parlay as % of total handle

# ─── UNIVERSE ─────────────────────────────────────────────────────────────────

OPERATORS = [
    ("DKNG", "DraftKings"),
    ("PENN", "Penn Ent."),
    ("FLUT", "Flutter/FanDuel"),
    ("MGM",  "MGM Resorts"),
    ("CZR",  "Caesars"),
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
            return c[-1], round(ret, 2)
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

# ─── BUILD CONTEXT ────────────────────────────────────────────────────────────

def build_bar_data(ops_data):
    """Bar chart: sorted descending, pct widths relative to max abs."""
    valid = [(sym, name, p, r)
             for (sym, name), (p, r) in zip(OPERATORS, ops_data)
             if r is not None]
    if not valid:
        return []
    valid_sorted = sorted(valid, key=lambda x: x[3], reverse=True)
    max_abs = max(abs(x[3]) for x in valid_sorted) or 1.0
    return [
        {
            "name":  name,
            "pct":   round(abs(ret) / max_abs * 100, 1),
            "pos":   ret >= 0,
            "label": f"{ret:+.1f}%",
        }
        for sym, name, price, ret in valid_sorted
    ]


def build_spark(betz_prices, spy_prices, svg_width=400, svg_height=140):
    """Compute SVG path data for BETZ vs SPY normalized sparkline."""
    if not betz_prices or not spy_prices:
        return None
    n = min(len(betz_prices), len(spy_prices))
    if n < 4:
        return None

    bp = betz_prices[-n:]
    sp = spy_prices[-n:]
    bn = [p / bp[0] * 100 for p in bp]
    sn = [p / sp[0] * 100 for p in sp]

    all_vals = bn + sn
    min_v    = min(all_vals)
    max_v    = max(all_vals)
    pad      = max((max_v - min_v) * 0.12, 0.5)
    min_v   -= pad
    max_v   += pad
    rng      = max_v - min_v

    def pts(vals):
        out = []
        for i, v in enumerate(vals):
            x = i / (n - 1) * svg_width
            y = svg_height - (v - min_v) / rng * svg_height
            out.append(f"{x:.1f},{y:.1f}")
        return " ".join(out)

    baseline_y = svg_height - (100 - min_v) / rng * svg_height
    betz_line  = pts(bn)
    # Close polygon to bottom-left for fill
    betz_poly  = betz_line + f" {svg_width:.1f},{svg_height:.1f} 0,{svg_height:.1f}"

    return {
        "betz_line":      betz_line,
        "betz_poly":      betz_poly,
        "spy_line":       pts(sn),
        "baseline_y":     round(baseline_y, 1),
        "baseline_y_pct": round((baseline_y / svg_height) * 100, 1),
        "betz_pct":       round(bn[-1] - 100, 1),
        "spy_pct":        round(sn[-1] - 100, 1),
        "n_days":         n,
        "height":         svg_height,
    }


def build_stat_rows(ops_data, spy_ret, betz_prices, vix):
    valid = [(sym, name, p, r)
             for (sym, name), (p, r) in zip(OPERATORS, ops_data)
             if r is not None]
    spy_r = spy_ret or 0.0

    rows = []
    if valid:
        top = max(valid, key=lambda x: x[3])
        bot = min(valid, key=lambda x: x[3])
        avg = sum(x[3] for x in valid) / len(valid)
        rows.append({"label": f"Top — {top[0]}", "value": f"{top[3]:+.1f}%",
                     "cls": "pos" if top[3] >= 0 else "neg"})
        rows.append({"label": f"Worst — {bot[0]}", "value": f"{bot[3]:+.1f}%",
                     "cls": "pos" if bot[3] >= 0 else "neg"})
        rows.append({"label": "Sector avg (5d)", "value": f"{avg:+.1f}%",
                     "cls": "pos" if avg >= 0 else "neg"})

    if spy_ret is not None:
        rows.append({"label": "S&P 500 (5d)", "value": f"{spy_r:+.1f}%",
                     "cls": "pos" if spy_r >= 0 else "neg"})
    if vix is not None:
        vix_cls = "neg" if vix > 25 else ("amber" if vix > 18 else "dim")
        rows.append({"label": "VIX", "value": f"{vix:.1f}", "cls": vix_cls})
    if betz_prices and len(betz_prices) >= 6:
        betz5d = (betz_prices[-1] / betz_prices[-6] - 1) * 100
        rows.append({"label": "BETZ ETF (5d)", "value": f"{betz5d:+.1f}%",
                     "cls": "pos" if betz5d >= 0 else "neg"})

    rows.append({"label": "Live Betting (AGA 2026)",  "value": f"{LIVE_BETTING_PCT}% of handle", "cls": "brand"})
    rows.append({"label": "Parlay Handle (AGA 2026)", "value": f"{PARLAY_PCT}% of handle",       "cls": "brand"})
    return rows


def build_subhead(ops_data, spy_ret):
    valid = [(sym, name, p, r)
             for (sym, name), (p, r) in zip(OPERATORS, ops_data)
             if r is not None]
    spy_r = spy_ret or 0.0
    if not valid:
        return "Sports betting sector — weekly snapshot"
    avg = sum(x[3] for x in valid) / len(valid)
    top = max(valid, key=lambda x: x[3])
    bot = min(valid, key=lambda x: x[3])
    if avg > spy_r + 2:
        return f"Sportsbooks beating market — sector avg {avg:+.1f}% vs SPY {spy_r:+.1f}%"
    elif avg < spy_r - 2:
        return f"Sportsbooks lagging market — sector avg {avg:+.1f}% vs SPY {spy_r:+.1f}%"
    elif top[3] > 5:
        return f"{top[1]} leads operators this week at {top[3]:+.1f}%"
    else:
        return f"{top[0]}: {top[3]:+.1f}%  ·  {bot[0]}: {bot[3]:+.1f}%  ·  SPY: {spy_r:+.1f}%"


# ─── RENDER ───────────────────────────────────────────────────────────────────

def render_card(ops_data, betz_prices, spy_prices, spy_ret, vix):
    spark = build_spark(betz_prices, spy_prices)

    ctx = {
        "date":      datetime.now().strftime("%b %d, %Y"),
        "timestamp": TIMESTAMP,
        "subhead":   build_subhead(ops_data, spy_ret),
        "bars":      build_bar_data(ops_data),
        "spark":     spark,
        "stats":     build_stat_rows(ops_data, spy_ret, betz_prices, vix),
        "cta_link":  _CTA_LINK,
        "cta_label": _CTA_LABEL,
    }

    env      = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("betting_card.html")
    html     = template.render(**ctx)

    tmp_html = SCRATCHPAD / f"betting_card_{TODAY}.html"
    tmp_html.write_text(html, encoding="utf-8")

    print(f"  Rendering via Chrome headless → {OUT_PATH}")
    render_html_to_png(tmp_html, OUT_PATH)
    print("  Running quality check...")
    quality_check(OUT_PATH)
    print(f"  Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching operator data (5d)...")
    ops_data = []
    for sym, name in OPERATORS:
        print(f"  {sym}...")
        p, r = fetch_5d(sym)
        ops_data.append((p, r))
        time.sleep(0.3)

    print("Fetching BETZ + SPY + VIX...")
    betz_prices = fetch_30d("BETZ")
    spy_prices  = fetch_30d("SPY")
    _, spy_ret  = fetch_5d("SPY")
    vix, _      = fetch_5d("^VIX")

    print("Rendering card...")
    render_card(ops_data, betz_prices, spy_prices, spy_ret, vix)
    print("Done.")


if __name__ == "__main__":
    main()
