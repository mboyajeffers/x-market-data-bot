#!/usr/bin/env python3
"""
Crypto Market Snapshot — X card generator
Output: cards/crypto_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #0d1117 background | #a855f7 purple | white text
Data: CoinGecko public API (no key required) + Alternative.me Fear & Greed + OKX Futures
"""

import json
import math
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


def okx_get(path, max_retries=3):
    """Fetch from OKX public API — no auth required, no US geo-block."""
    url = f"https://www.okx.com{path}"
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(3)
    return None


def fetch_btc_funding_rate():
    """Returns (rate_pct, label) — latest BTC-USD-SWAP 8hr funding rate via OKX.
    Verifiable at: okx.com/api/v5/public/funding-rate?instId=BTC-USD-SWAP
    """
    data = okx_get("/api/v5/public/funding-rate?instId=BTC-USD-SWAP")
    if data and data.get("code") == "0" and data.get("data"):
        entry = data["data"][0]
        raw   = float(entry.get("fundingRate") or entry.get("settFundingRate") or 0)
        rate  = raw * 100
        if rate > 0.05:
            label = "CROWDED LONGS"
        elif rate > 0.01:
            label = "LONGS PAYING"
        elif rate < -0.01:
            label = "SHORTS PAYING"
        else:
            label = "NEUTRAL"
        return round(rate, 4), label
    return None, None


def fetch_btc_oi():
    """Returns BTC open interest in USD via OKX BTC-USD-SWAP.
    Verifiable at: okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USD-SWAP
    """
    data = okx_get("/api/v5/public/open-interest?instType=SWAP&instId=BTC-USD-SWAP")
    if data and data.get("code") == "0" and data.get("data"):
        return float(data["data"][0].get("oiUsd") or 0)
    return None

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.gridspec as gridspec  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from card_spec import (  # noqa: E402
    FONT_TITLE, FONT_HEADLINE, FONT_HANDLE,
    FONT_LABEL, FONT_SMALL, FONT_TINY,
    GS_TOP, GS_BOTTOM, GS_WSPACE,
    HDR_TITLE_Y, HDR_HEADLINE_Y, HDR_STAT_Y, HDR_HANDLE_Y,
    FOOTER_Y, MARGIN_LEFT, MARGIN_RIGHT,
)
from card_validator import detect_and_fix_overlaps  # noqa: E402


# ─── PATHS ────────────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent.parent / "cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)
_now_utc  = datetime.now(timezone.utc)
TODAY     = _now_utc.strftime("%Y-%m-%d")
TIMESTAMP = _now_utc.strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"crypto_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG           = "#0a0e14"   # site --bg-primary
PURPLE       = "#a855f7"   # crypto accent: bright purple (CLAUDE.md #9333ea family)
GREEN        = "#22c55e"
RED          = "#ef4444"
AMBER        = "#f59e0b"
GREY         = "#64748b"   # site --text-muted
WHITE        = "#f1f5f9"   # site --text-primary
DIM          = "#94a3b8"   # site --text-secondary
CARD_BG      = "#1a2130"   # site --bg-card
PANEL_BORDER = "#2a3441"   # site --border-color

# ─── COINGECKO ────────────────────────────────────────────────────────────────

def coingecko_get(path, max_retries=3):
    url = f"https://api.coingecko.com/api/v3{path}"
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = (attempt + 1) * 25
                print(f"  CoinGecko 429 — waiting {wait}s")
                time.sleep(wait)
                continue
            print(f"ERROR: CoinGecko HTTP {e.code} on {path}")
            sys.exit(1)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(8)
                continue
            print(f"ERROR: CoinGecko fetch failed on {path}: {e}")
            sys.exit(1)
    print(f"ERROR: CoinGecko {path} failed after {max_retries} retries")
    sys.exit(1)


def fetch_markets(per_page=20):
    path = (
        f"/coins/markets"
        f"?vs_currency=usd"
        f"&order=market_cap_desc"
        f"&per_page={per_page}"
        f"&page=1"
        f"&sparkline=false"
        f"&price_change_percentage=7d,24h"
    )
    return coingecko_get(path)


def fetch_coin_history(coin_id, days=30):
    path = f"/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    data = coingecko_get(path)
    return [p[1] for p in data["prices"]]


def fetch_global():
    gd = coingecko_get("/global")["data"]
    return {
        "btc_dominance":       gd["market_cap_percentage"].get("btc", 0),
        "eth_dominance":       gd["market_cap_percentage"].get("eth", 0),
        "total_market_cap_usd": gd["total_market_cap"]["usd"],
    }


def fetch_fear_greed():
    url = "https://api.alternative.me/fng/?limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            entries = json.loads(resp.read().decode())["data"]
        return int(entries[0]["value"]), entries[0]["value_classification"]
    except Exception as e:
        print(f"ERROR: Fear & Greed fetch failed: {e}")
        sys.exit(1)

# ─── RISK METRICS ─────────────────────────────────────────────────────────────

def compute_metrics(prices):
    """
    Returns risk metrics for a price series.
    Uses 30-day cumulative return (not annualized) to avoid nonsensical
    annualized figures from short volatile windows.
    """
    if len(prices) < 2:
        raise ValueError("Insufficient price history")
    returns = [math.log(prices[i] / prices[i-1]) for i in range(1, len(prices)) if prices[i-1] > 0]
    n = len(returns)
    mean_r   = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    daily_vol = math.sqrt(variance)
    ann_vol   = daily_vol * math.sqrt(252) * 100
    rf_daily  = 4.5 / 252 / 100
    sharpe    = ((mean_r - rf_daily) / daily_vol * math.sqrt(252)) if daily_vol > 0 else 0
    var_95    = -(mean_r - 1.645 * daily_vol) * 100
    peak = prices[0]
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (p - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd
    # 30-day cumulative return (accurate; no annualization)
    ret_30d = (prices[-1] / prices[0] - 1) * 100
    return {
        "ann_vol": ann_vol,
        "ret_30d": ret_30d,
        "sharpe":  sharpe,
        "var_95":  var_95,
        "max_dd":  max_dd,
    }

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def format_crypto_label(m):
    """Format bar chart label as 'SYM · Name' with name truncated."""
    sym  = m["symbol"].upper()
    name = m.get("name", "")
    if not name or name.lower() == sym.lower():
        return sym
    display = name if len(name) <= 10 else name[:9] + "."
    return f"{sym} · {display}"

# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(markets, global_data, btc_metrics, eth_metrics, fg_value, fg_label,
              btc_fr=None, btc_fr_label=None, btc_oi=None):

    # Dynamic insight headline
    returns_7d = [m["price_change_percentage_7d_in_currency"]
                  for m in markets
                  if m.get("price_change_percentage_7d_in_currency") is not None]
    avg_7d = sum(returns_7d) / len(returns_7d) if returns_7d else 0
    btc_dom = global_data["btc_dominance"]

    if fg_value <= 25:
        headline = f"Sentiment: {fg_label} ({fg_value}) — fear dominates the market"
    elif fg_value >= 75:
        headline = f"Sentiment: {fg_label} ({fg_value}) — watch for overextension"
    elif avg_7d > 10:
        headline = f"Strong week: top 20 assets avg +{avg_7d:.1f}% — broad-based rally"
    elif avg_7d < -8:
        headline = f"Risk-off week: top 20 assets avg {avg_7d:.1f}% — broad decline"
    elif btc_dom > 58:
        headline = f"BTC dominance at {btc_dom:.1f}% — capital consolidating in Bitcoin"
    elif btc_dom < 44:
        headline = f"Alt season dynamics: BTC dominance at {btc_dom:.1f}%"
    else:
        headline = f"Fear & Greed: {fg_value} ({fg_label})  |  BTC dominance: {btc_dom:.1f}%"

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    # Top accent stripe
    fig.add_artist(plt.Line2D([0, 1], [0.993, 0.993],
                              transform=fig.transFigure, color=PURPLE, linewidth=2.5,
                              solid_capstyle="butt", zorder=10))

    gs = gridspec.GridSpec(
        1, 3,
        figure=fig,
        width_ratios=[4.2, 2.9, 2.9],
        left=0.04, right=0.97,
        top=GS_TOP, bottom=GS_BOTTOM,
        wspace=GS_WSPACE,
    )

    ax_bars  = fig.add_subplot(gs[0, 0])
    ax_risk  = fig.add_subplot(gs[0, 1])
    ax_stats = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_risk, ax_stats]:
        ax.set_facecolor(CARD_BG)
        for spine in ax.spines.values():
            spine.set_edgecolor(PANEL_BORDER)

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, HDR_TITLE_Y, f"Crypto Market Snapshot — {TODAY}",
             fontsize=FONT_TITLE, fontweight="bold", color=WHITE, va="top")
    fig.text(MARGIN_LEFT, HDR_HEADLINE_Y, headline,
             fontsize=FONT_HEADLINE, color=PURPLE, va="top")
    fig.text(MARGIN_RIGHT, HDR_STAT_Y, f"Fear & Greed: {fg_value} — {fg_label}",
             fontsize=FONT_HEADLINE, color=PURPLE, va="top", ha="right")
    fig.text(MARGIN_RIGHT, HDR_HANDLE_Y, "@Mboya_Jeffers",
             fontsize=FONT_HANDLE, color=PURPLE, va="top", ha="right", fontweight="bold")

    # ── LEFT: BAR CHART (7d return, top5 + bottom3) ───────────────────────────
    sorted_by_7d = sorted(
        [m for m in markets if m.get("price_change_percentage_7d_in_currency") is not None],
        key=lambda x: x["price_change_percentage_7d_in_currency"]
    )
    bottom3 = sorted_by_7d[:3]
    top5    = sorted_by_7d[-5:]
    display = bottom3 + top5

    labels = [format_crypto_label(m) for m in display]
    values = [m["price_change_percentage_7d_in_currency"] for m in display]
    colors = [GREEN if v >= 0 else RED for v in values]

    y_pos = range(len(labels))
    ax_bars.barh(list(y_pos), values, color=colors, height=0.65, alpha=0.85)
    ax_bars.set_yticks(list(y_pos))
    ax_bars.set_yticklabels(labels, fontsize=FONT_LABEL, color=WHITE)
    ax_bars.tick_params(axis="x", labelsize=FONT_SMALL, colors=DIM)
    ax_bars.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
    ax_bars.set_title("7-Day Return (%)", fontsize=FONT_HEADLINE, color=DIM, pad=6)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
    ax_bars.grid(axis="x", color=PANEL_BORDER, linewidth=0.5, alpha=0.7)

    # Dynamic xlim — prevents label clipping
    xmin = min(values)
    xmax = max(values) if max(values) > 0 else 0.5
    buf  = (xmax - xmin) * 0.22
    ax_bars.set_xlim(xmin - buf, xmax + buf)
    offset = (xmax - xmin) * 0.03

    for i, (v, c) in enumerate(zip(values, colors)):
        ha = "left" if v >= 0 else "right"
        ax_bars.text(v + (offset if v >= 0 else -offset), i,
                     f"{v:+.1f}%", va="center", ha=ha, fontsize=FONT_TINY, color=c)

    # ── CENTER: RISK TABLE (BTC + ETH) ────────────────────────────────────────
    ax_risk.axis("off")
    ax_risk.set_title("Risk Metrics", fontsize=FONT_HEADLINE, color=DIM, pad=6)

    risk_data = [
        ("",              "BTC",                               "ETH"),
        ("VaR 95% (1d)", f"{btc_metrics['var_95']:.2f}%",    f"{eth_metrics['var_95']:.2f}%"),
        ("Sharpe (ann.)", f"{btc_metrics['sharpe']:.2f}",     f"{eth_metrics['sharpe']:.2f}"),
        ("Max Drawdown",  f"{btc_metrics['max_dd']:.1f}%",    f"{eth_metrics['max_dd']:.1f}%"),
        ("Ann. Vol",      f"{btc_metrics['ann_vol']:.1f}%",   f"{eth_metrics['ann_vol']:.1f}%"),
        ("30d Return",    f"{btc_metrics['ret_30d']:+.1f}%",  f"{eth_metrics['ret_30d']:+.1f}%"),
    ]

    row_h  = 0.145
    col_x  = [0.04, 0.52, 0.81]   # value cols pushed right so larger labels (e.g. "Max Drawdown") don't collide
    y_start = 0.83

    ax_risk.text(col_x[1], y_start, "BTC", fontsize=FONT_HEADLINE, fontweight="bold",
                 color=PURPLE, transform=ax_risk.transAxes, ha="center")
    ax_risk.text(col_x[2], y_start, "ETH", fontsize=FONT_HEADLINE, fontweight="bold",
                 color=PURPLE, transform=ax_risk.transAxes, ha="center")

    for i, row in enumerate(risk_data[1:]):
        y = y_start - (i + 1) * row_h
        bg_color = "#0a0f18" if i % 2 == 0 else CARD_BG
        rect = FancyBboxPatch((0, y - 0.01), 1.0, row_h,
                              boxstyle="round,pad=0.01",
                              facecolor=bg_color, edgecolor="none",
                              transform=ax_risk.transAxes, clip_on=False)
        ax_risk.add_patch(rect)
        ax_risk.text(col_x[0], y + 0.045, row[0], fontsize=FONT_LABEL, color=DIM,
                     transform=ax_risk.transAxes, va="center")

        for j, val in enumerate([row[1], row[2]]):
            color = WHITE
            if "%" in val:
                try:
                    num = float(val.replace("%", "").replace("+", ""))
                    if row[0] in ("Max Drawdown", "VaR 95% (1d)"):
                        color = RED if num > 3 else WHITE
                    elif row[0] == "30d Return":
                        color = GREEN if num > 0 else RED
                except ValueError:
                    pass
            ax_risk.text(col_x[j+1], y + 0.045, val, fontsize=FONT_LABEL, color=color,
                         transform=ax_risk.transAxes, ha="center", va="center")

    ax_risk.text(0.5, 0.02, "30-day data  |  RF: 4.5%  |  Log returns",
                 fontsize=FONT_TINY, color=GREY, transform=ax_risk.transAxes,
                 ha="center", style="italic")

    # ── RIGHT: GLOBAL STATS ────────────────────────────────────────────────────
    ax_stats.axis("off")
    ax_stats.set_title("Market Overview", fontsize=FONT_HEADLINE, color=DIM, pad=6)

    btc_price = next((m["current_price"] for m in markets if m["symbol"] == "btc"), None)
    eth_price = next((m["current_price"] for m in markets if m["symbol"] == "eth"), None)
    eth_btc_ratio = (eth_price / btc_price) if (btc_price and eth_price) else None
    total_mcap = global_data["total_market_cap_usd"] / 1e12

    stats = [
        ("BTC Dominance",  f"{global_data['btc_dominance']:.1f}%"),
        ("ETH Dominance",  f"{global_data['eth_dominance']:.1f}%"),
        ("Total Mkt Cap",  f"${total_mcap:.2f}T"),
        ("ETH/BTC Ratio",  f"{eth_btc_ratio:.5f}" if eth_btc_ratio else "N/A"),
        ("Avg 7d Return",  f"{avg_7d:+.2f}%"),
        ("Assets Tracked", f"{len(returns_7d)} / 20"),
    ]
    # Practitioner layer: BTC funding rate + open interest (cascade risk signals)
    if btc_fr is not None:
        stats.append(("BTC Funding (8hr)", f"{btc_fr:+.4f}% {btc_fr_label or ''}"))
    if btc_oi is not None:
        stats.append(("BTC OI (contracts)", f"{btc_oi/1000:.1f}K"))

    row_h2 = 0.11
    y2 = 0.82
    for label, val in stats:
        val_color = WHITE
        if label == "Avg 7d Return":
            try:
                num = float(val.replace("%", "").replace("+", ""))
                val_color = GREEN if num > 0 else RED
            except ValueError:
                pass
        elif label == "BTC Funding (8hr)":
            if btc_fr is not None:
                val_color = RED if btc_fr > 0.03 else (AMBER if btc_fr > 0.01 else
                            (GREEN if btc_fr < -0.01 else WHITE))

        ax_stats.text(0.06, y2, label, fontsize=FONT_LABEL, color=DIM,
                      transform=ax_stats.transAxes, va="top")
        ax_stats.text(0.94, y2, val, fontsize=FONT_SMALL, color=val_color,
                      fontweight="bold", transform=ax_stats.transAxes,
                      ha="right", va="top")
        ax_stats.add_artist(plt.Line2D(
            [0.03, 0.97], [y2 - 0.015, y2 - 0.015],
            transform=ax_stats.transAxes, color="#21262d", linewidth=0.5,
        ))
        y2 -= row_h2

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, FOOTER_Y, f"Source: CoinGecko · OKX  |  Generated: {TIMESTAMP}",
             fontsize=FONT_SMALL, color=GREY, va="top")
    fig.text(MARGIN_RIGHT, FOOTER_Y, "@Mboya_Jeffers",
             fontsize=FONT_SMALL, color=PURPLE, va="top", ha="right")

    fig.add_artist(plt.Line2D([0.04, 0.97], [0.107, 0.107],
                              transform=fig.transFigure,
                              color=PANEL_BORDER, linewidth=0.8))

    
    detect_and_fix_overlaps(fig)
    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching CoinGecko markets (top 20)...")
    markets = fetch_markets(20)
    if not markets:
        print("ERROR: No market data returned")
        sys.exit(1)

    print("Fetching BTC price history (30d)...")
    btc_prices = fetch_coin_history("bitcoin", days=30)

    print("Fetching ETH price history (30d)...")
    eth_prices = fetch_coin_history("ethereum", days=30)

    print("Fetching global market data...")
    global_data = fetch_global()

    print("Fetching Fear & Greed...")
    fg_value, fg_label = fetch_fear_greed()

    print("Computing risk metrics...")
    btc_metrics = compute_metrics(btc_prices)
    eth_metrics = compute_metrics(eth_prices)

    print("Fetching Binance: BTC funding rate...")
    btc_fr, btc_fr_label = fetch_btc_funding_rate()
    if btc_fr is not None:
        print(f"  BTC funding: {btc_fr:+.4f}% ({btc_fr_label})")

    print("Fetching Binance: BTC open interest...")
    btc_oi = fetch_btc_oi()
    if btc_oi is not None:
        print(f"  BTC OI: {btc_oi/1000:.1f}K contracts")

    print("Drawing card...")
    draw_card(markets, global_data, btc_metrics, eth_metrics, fg_value, fg_label,
              btc_fr=btc_fr, btc_fr_label=btc_fr_label, btc_oi=btc_oi)
    print("Done.")


if __name__ == "__main__":
    main()
