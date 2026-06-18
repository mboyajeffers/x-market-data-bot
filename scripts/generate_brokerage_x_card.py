#!/usr/bin/env python3
"""
Brokerage Market Snapshot — X card generator
Output: REVENUE/X/cards/brokerage_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #080f1e background | #1e3a5f navy | white text
Data: Yahoo Finance (broker stocks + options volume + market breadth)
"""

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

OUT_DIR = Path("/Users/mboyajeffers/Claude_Projects/REVENUE/X/cards")
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY = datetime.now().strftime("%Y-%m-%d")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH = OUT_DIR / f"brokerage_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG      = "#080f1e"
NAVY    = "#1e3a5f"
BLUE    = "#3b82f6"
GREEN   = "#22c55e"
RED     = "#ef4444"
GREY    = "#6b7280"
WHITE   = "#f1f5f9"
DIM     = "#94a3b8"
CARD_BG = "#0f1a2e"

# ─── BROKER UNIVERSE ──────────────────────────────────────────────────────────

BROKERS = [
    ("SCHW",  "Charles Schwab"),
    ("IBKR",  "Interactive Brokers"),
    ("MS",    "Morgan Stanley"),
    ("GS",    "Goldman Sachs"),
    ("TD",    "TD Bank"),
    ("HOOD",  "Robinhood"),
    ("MKTX", "MarketAxess"),
    ("VIRT",  "Virtu Financial"),
]

MARKET_TICKERS = [
    ("SPY",  "S&P 500 ETF"),
    ("QQQ",  "Nasdaq-100 ETF"),
    ("IWM",  "Russell 2000 ETF"),
    ("DIA",  "Dow Jones ETF"),
]


def fetch_5d_return(ticker, max_retries=3):
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="10d")
            if hist.empty or len(hist) < 2:
                raise RuntimeError(f"{ticker}: insufficient history")
            closes = hist["Close"].dropna().tolist()
            ret5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else \
                    (closes[-1] - closes[0]) / closes[0] * 100
            return closes[-1], ret5d
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            print(f"  WARNING: {ticker} failed: {e}")
            return None, None


def fetch_options_activity(ticker, max_retries=3):
    """Get options volume (calls + puts) from the nearest expiration."""
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            exps = t.options
            if not exps:
                return None
            # Get nearest expiry
            chain = t.option_chain(exps[0])
            call_vol = int(chain.calls["volume"].fillna(0).sum())
            put_vol  = int(chain.puts["volume"].fillna(0).sum())
            pcr = put_vol / call_vol if call_vol > 0 else None
            return {"calls": call_vol, "puts": put_vol, "pcr": pcr, "expiry": exps[0]}
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(4)
                continue
            print(f"  WARNING: options for {ticker} failed: {e}")
            return None


def fetch_vix(max_retries=3):
    for attempt in range(max_retries):
        try:
            t = yf.Ticker("^VIX")
            hist = t.history(period="5d")
            if hist.empty:
                raise RuntimeError("VIX empty")
            closes = hist["Close"].dropna().tolist()
            ret5d = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
            return closes[-1], ret5d
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            print(f"  WARNING: VIX failed: {e}")
            return 20.0, 0.0


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(broker_data, market_data, spy_opts, spy_price, spy_ret5d, vix, vix_ret1d):
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    gs = gridspec.GridSpec(
        1, 3,
        figure=fig,
        width_ratios=[4, 3, 3],
        left=0.02, right=0.98,
        top=0.82, bottom=0.13,
        wspace=0.33,
    )

    ax_bars   = fig.add_subplot(gs[0, 0])
    ax_opts   = fig.add_subplot(gs[0, 1])
    ax_market = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_opts, ax_market]:
        ax.set_facecolor(CARD_BG)
        for spine in ax.spines.values():
            spine.set_edgecolor("#0f1f38")

    # Dynamic insight headline
    if vix > 25:
        headline = f"VIX at {vix:.1f} — elevated volatility, broker flows under pressure"
    elif spy_opts and spy_opts.get("pcr") and spy_opts["pcr"] > 1.5:
        headline = f"Put/Call ratio: {spy_opts['pcr']:.2f} — options market skewing bearish"
    elif spy_opts and spy_opts.get("pcr") and spy_opts["pcr"] < 0.6:
        headline = f"Put/Call ratio: {spy_opts['pcr']:.2f} — options market skewing bullish"
    elif broker_data:
        top_b = max(broker_data, key=lambda x: x["ret5d"])
        bot_b = min(broker_data, key=lambda x: x["ret5d"])
        if top_b["ret5d"] > 4:
            headline = f"{top_b['name']} leads brokers this week at +{top_b['ret5d']:.1f}%"
        elif bot_b["ret5d"] < -4:
            headline = f"{bot_b['name']} lags brokers at {bot_b['ret5d']:.1f}% — weak week for sector"
        else:
            headline = f"Broker sector mixed: SPY {spy_ret5d:+.1f}% this week  |  VIX: {vix:.1f}"
    else:
        headline = f"SPY {spy_ret5d:+.1f}% this week  |  VIX: {vix:.1f}"

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.93, f"Brokerage Sector Snapshot — {TODAY}",
             fontsize=14, fontweight="bold", color=WHITE, va="top")
    fig.text(0.02, 0.88, headline,
             fontsize=9, color=BLUE, va="top")
    vix_color = RED if vix > 25 else (WHITE if vix > 18 else GREEN)
    fig.text(0.98, 0.92,
             f"SPY: \\${spy_price:.2f}  ({spy_ret5d:+.1f}% 5d)  |  VIX: {vix:.1f}  ({vix_ret1d:+.1f}% 1d)",
             fontsize=8.5, color=vix_color, va="top", ha="right")
    fig.text(0.98, 0.86, "@Mboya_Jeffers",
             fontsize=8.5, color=BLUE, va="top", ha="right", fontweight="bold")

    # ── LEFT: BROKER BAR CHART ────────────────────────────────────────────────
    sorted_brokers = sorted(broker_data, key=lambda x: x["ret5d"])
    labels = [b["name"] for b in sorted_brokers]
    values = [b["ret5d"] for b in sorted_brokers]
    colors = [GREEN if v >= 0 else RED for v in values]

    y_pos = range(len(labels))
    ax_bars.barh(list(y_pos), values, color=colors, height=0.65, alpha=0.85)
    ax_bars.set_yticks(list(y_pos))
    ax_bars.set_yticklabels(labels, fontsize=7.5, color=WHITE)
    ax_bars.tick_params(axis="x", labelsize=7, colors=DIM)
    ax_bars.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
    ax_bars.set_title("5-Day Broker Return (%)", fontsize=9, color=DIM, pad=6)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
    ax_bars.grid(axis="x", color="#0f1f38", linewidth=0.5, alpha=0.7)

    for i, (v, c) in enumerate(zip(values, colors)):
        ha = "left" if v >= 0 else "right"
        offset = 0.06 if v >= 0 else -0.06
        ax_bars.text(v + offset, i, f"{v:+.2f}%", va="center", ha=ha,
                     fontsize=6.5, color=c)

    # ── CENTER: SPY OPTIONS FLOW ───────────────────────────────────────────────
    ax_opts.axis("off")
    ax_opts.set_title("SPY Options Flow", fontsize=9, color=DIM, pad=6)

    if spy_opts:
        total_vol = spy_opts["calls"] + spy_opts["puts"]
        call_pct = spy_opts["calls"] / total_vol * 100 if total_vol > 0 else 50
        put_pct  = spy_opts["puts"]  / total_vol * 100 if total_vol > 0 else 50
        pcr = spy_opts["pcr"]
        expiry = spy_opts["expiry"]

        # Visual call/put bar
        bar_y = 0.72
        ax_opts.add_patch(FancyBboxPatch((0.05, bar_y), 0.9 * call_pct / 100, 0.08,
                                         boxstyle="round,pad=0",
                                         facecolor=GREEN, edgecolor="none",
                                         transform=ax_opts.transAxes, clip_on=True))
        ax_opts.add_patch(FancyBboxPatch((0.05 + 0.9 * call_pct / 100, bar_y),
                                          0.9 * put_pct / 100, 0.08,
                                          boxstyle="round,pad=0",
                                          facecolor=RED, edgecolor="none",
                                          transform=ax_opts.transAxes, clip_on=True))

        ax_opts.text(0.5, 0.67, f"Calls {call_pct:.0f}%  /  Puts {put_pct:.0f}%",
                     fontsize=8, color=DIM, transform=ax_opts.transAxes, ha="center")

        opts_rows = [
            ("Call Volume", f"{spy_opts['calls']:,}"),
            ("Put Volume",  f"{spy_opts['puts']:,}"),
            ("Total Volume", f"{total_vol:,}"),
            ("Put/Call Ratio", f"{pcr:.3f}" if pcr else "N/A"),
            ("Nearest Expiry", expiry),
        ]

        row_h = 0.10
        y = 0.58
        for label, val in opts_rows:
            ax_opts.text(0.06, y, label, fontsize=8, color=DIM,
                         transform=ax_opts.transAxes, va="top")
            val_color = WHITE
            if label == "Put/Call Ratio" and pcr:
                val_color = RED if pcr > 1.2 else (GREEN if pcr < 0.8 else WHITE)
            ax_opts.text(0.94, y, val, fontsize=8.5, color=val_color,
                         fontweight="bold", transform=ax_opts.transAxes,
                         ha="right", va="top")
            ax_opts.add_artist(plt.Line2D(
                [0.03, 0.97], [y - 0.015, y - 0.015],
                transform=ax_opts.transAxes, color="#0f1f38", linewidth=0.5,
            ))
            y -= row_h

        bias = "BEARISH" if (pcr and pcr > 1.2) else ("BULLISH" if (pcr and pcr < 0.8) else "NEUTRAL")
        bias_color = RED if bias == "BEARISH" else (GREEN if bias == "BULLISH" else DIM)
        ax_opts.text(0.5, 0.08, f"Options Bias: {bias}",
                     fontsize=9, color=bias_color, fontweight="bold",
                     transform=ax_opts.transAxes, ha="center")
    else:
        ax_opts.text(0.5, 0.5, "Options data\nunavailable",
                     fontsize=10, color=DIM, transform=ax_opts.transAxes,
                     ha="center", va="center")

    ax_opts.text(0.5, 0.02, "Yahoo Finance  |  Front-month expiry",
                 fontsize=6, color=GREY, transform=ax_opts.transAxes,
                 ha="center", style="italic")

    # ── RIGHT: BROAD MARKET ────────────────────────────────────────────────────
    ax_market.axis("off")
    ax_market.set_title("Broad Market", fontsize=9, color=DIM, pad=6)

    row_h2 = 0.13
    y2 = 0.85
    for item in market_data:
        val_color = GREEN if item["ret5d"] >= 0 else RED
        ax_market.text(0.06, y2, item["name"], fontsize=8, color=DIM,
                       transform=ax_market.transAxes, va="top")
        ax_market.text(0.94, y2, f"{item['ret5d']:+.2f}%", fontsize=8.5, color=val_color,
                       fontweight="bold", transform=ax_market.transAxes,
                       ha="right", va="top")
        ax_market.add_artist(plt.Line2D(
            [0.03, 0.97], [y2 - 0.015, y2 - 0.015],
            transform=ax_market.transAxes, color="#0f1f38", linewidth=0.5,
        ))
        y2 -= row_h2

    # VIX block
    y2 -= 0.04
    vix_bg = RED if vix > 25 else (NAVY if vix > 18 else "#0f2a1a")
    rect = FancyBboxPatch((0.03, y2 - 0.05), 0.94, 0.18,
                          boxstyle="round,pad=0.02",
                          facecolor=vix_bg, edgecolor="none",
                          transform=ax_market.transAxes, clip_on=False)
    ax_market.add_patch(rect)
    ax_market.text(0.5, y2 + 0.07, f"VIX  {vix:.1f}  ({vix_ret1d:+.1f}% 1d)",
                   fontsize=10, color=WHITE, fontweight="bold",
                   transform=ax_market.transAxes, ha="center", va="center")

    regime = "High Volatility" if vix > 25 else ("Elevated" if vix > 18 else "Low Volatility")
    ax_market.text(0.5, y2 - 0.04, regime,
                   fontsize=7.5, color=DIM,
                   transform=ax_market.transAxes, ha="center")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.06, f"Source: Yahoo Finance (equities + options chains)  |  Generated: {TIMESTAMP}",
             fontsize=7.5, color=GREY, va="top")
    fig.text(0.98, 0.06, "github.com/mboyajeffers/data-intelligence-platform",
             fontsize=7.5, color=BLUE, va="top", ha="right")

    fig.add_artist(plt.Line2D([0.02, 0.98], [0.105, 0.105],
                              transform=fig.transFigure,
                              color="#0f1f38", linewidth=0.8))

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching broker stock returns...")
    broker_data = []
    for sym, name in BROKERS:
        price, ret5d = fetch_5d_return(sym)
        if price is not None:
            broker_data.append({"ticker": sym, "name": name, "price": price, "ret5d": ret5d})
            time.sleep(0.25)

    print("Fetching broad market indices...")
    market_data = []
    for sym, name in MARKET_TICKERS:
        price, ret5d = fetch_5d_return(sym)
        if price is not None:
            market_data.append({"ticker": sym, "name": name, "price": price, "ret5d": ret5d})
            time.sleep(0.25)

    print("Fetching SPY options flow...")
    spy_opts = fetch_options_activity("SPY")
    if spy_opts:
        print(f"  Calls: {spy_opts['calls']:,}  Puts: {spy_opts['puts']:,}  PCR: {spy_opts['pcr']:.3f}")

    print("Fetching SPY price/return...")
    spy_price, spy_ret5d = fetch_5d_return("SPY")
    spy_price = spy_price or 500.0
    spy_ret5d = spy_ret5d or 0.0

    print("Fetching VIX...")
    vix, vix_ret1d = fetch_vix()
    print(f"  VIX: {vix:.1f}")

    print("Drawing card...")
    draw_card(broker_data, market_data, spy_opts, spy_price, spy_ret5d, vix, vix_ret1d)
    print("Done.")


if __name__ == "__main__":
    main()
