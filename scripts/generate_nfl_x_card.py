#!/usr/bin/env python3
"""
NFL — X Card Generator
Replaces the retired `worldcup` vertical (2026-08-26) — the 2026 World Cup
ended 2026-07-19; the NFL season starts 2026-09-09 and is the highest-volume
US sportsbook betting sport, making it the natural direct successor for this
posting slot. Runs weekly (not daily, unlike World Cup) since NFL games are
concentrated on Sun/Mon/Thu, not spread across every day.

Layout: matchups/schedule panel | sportsbook operator stock bar chart
Output: cards/nfl_x_card_YYYY-MM-DD.png (1200x675px)
Theme: reuses the "worldcup" accent (cyan/blue) as its direct successor.
"""

import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import yfinance as yf

from card_spec import (
    FONT_TITLE, FONT_HEADLINE, FONT_HANDLE,
    FONT_LABEL, FONT_SMALL, FONT_TINY,
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
OUT_PATH  = OUT_DIR / f"nfl_x_card_{TODAY}.png"

# ─── COLORS (reuses worldcup's cyan/blue as direct successor — see vertical_colors.py) ──

BG       = "#0a0e14"
CYAN     = "#00d4aa"
BLUE     = "#3b82f6"
GREEN    = "#22c55e"
RED      = "#ef4444"
GREY     = "#64748b"
WHITE    = "#f1f5f9"
DIM      = "#94a3b8"
CARD_BG  = "#1a2130"
BORDER   = "#2a3441"

SEASON_START = datetime(2026, 9, 9)

# Sportsbook operators — same universe betting.py tracks, since NFL season is
# the single biggest driver of sportsbook stock movement.
OPERATORS = [
    ("DKNG", "DraftKings"),
    ("FLUT", "Flutter/FanDuel"),
    ("PENN", "Penn Ent."),
    ("MGM",  "MGM Resorts"),
    ("CZR",  "Caesars"),
]


# ─── ESPN ─────────────────────────────────────────────────────────────────────

def fetch_nfl_scoreboard():
    """Current week's NFL scoreboard. Returns [] gracefully before/between weeks
    (e.g. now, before the 2026-09-09 season start) — caller shows a countdown
    instead."""
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        games = []
        for event in data.get("events", []):
            comp = event.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
            try:
                dt_utc = datetime.strptime(event.get("date", ""), "%Y-%m-%dT%H:%MZ")
                dt_et = dt_utc.replace(tzinfo=timezone.utc) - timedelta(hours=4)
                time_str = dt_et.strftime("%a %-I:%M%p ET")
            except Exception:
                time_str = event.get("status", {}).get("type", {}).get("shortDetail", "")
            games.append({
                "home": home.get("team", {}).get("abbreviation", "?"),
                "away": away.get("team", {}).get("abbreviation", "?"),
                "home_score": home.get("score", ""),
                "away_score": away.get("score", ""),
                "state": event.get("status", {}).get("type", {}).get("state", "pre"),
                "time": time_str,
            })
        return games
    except Exception:
        return []


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


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(games, stock_data, spy_ret):
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    fig.add_artist(plt.Line2D([0, 1], [0.993, 0.993],
                              transform=fig.transFigure, color=CYAN, linewidth=2.5,
                              solid_capstyle="butt", zorder=10))

    gs = gridspec.GridSpec(1, 2, figure=fig,
                           width_ratios=[5, 4.5],
                           left=0.02, right=0.98,
                           top=GS_TOP, bottom=GS_BOTTOM, wspace=GS_WSPACE)
    ax_games = fig.add_subplot(gs[0, 0])
    ax_bars  = fig.add_subplot(gs[0, 1])

    for ax in [ax_games, ax_bars]:
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)

    days_out = (SEASON_START - datetime.now()).days
    valid = [(sym, name, p, r) for (sym, name), (p, r) in zip(OPERATORS, stock_data)
             if r is not None]

    if games:
        headline = f"Week's slate — {len(games)} games"
    elif days_out > 0:
        headline = f"Season kicks off in {days_out} days — Sept 9, 2026"
    else:
        headline = "NFL season underway"

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, HDR_TITLE_Y, f"NFL — {TODAY}",
             fontsize=FONT_TITLE, fontweight="bold", color=WHITE, va="top")
    fig.text(MARGIN_LEFT, HDR_HEADLINE_Y, headline, fontsize=FONT_HEADLINE, color=CYAN, va="top")
    spy_c = GREEN if (spy_ret or 0) >= 0 else RED
    fig.text(MARGIN_RIGHT, HDR_STAT_Y, f"SPY: {spy_ret:+.1f}%" if spy_ret is not None else "SPY: n/a",
             fontsize=FONT_HEADLINE, color=spy_c, va="top", ha="right")
    fig.text(MARGIN_RIGHT, HDR_HANDLE_Y, "@Mboya_Jeffers",
             fontsize=FONT_HANDLE, color=CYAN, va="top", ha="right", fontweight="bold")

    # ── LEFT: GAMES / COUNTDOWN ───────────────────────────────────────────────
    ax_games.axis("off")
    ax_games.set_title("This Week" if games else "Countdown to Kickoff",
                       fontsize=FONT_HEADLINE, color=DIM, pad=6)

    if games:
        y = 0.90
        for g in games[:8]:
            if g["state"] == "post":
                line = f"{g['away']} {g['away_score']} @ {g['home']} {g['home_score']} — FINAL"
                color = DIM
            elif g["state"] == "in":
                line = f"🔴 {g['away']} {g['away_score']} @ {g['home']} {g['home_score']}"
                color = RED
            else:
                line = f"{g['away']} @ {g['home']} — {g['time']}"
                color = WHITE
            ax_games.text(0.05, y, line, fontsize=FONT_SMALL, color=color,
                          transform=ax_games.transAxes, va="top")
            y -= 0.10
    else:
        ax_games.text(0.5, 0.55, f"{max(days_out, 0)}",
                      fontsize=48, fontweight="bold", color=CYAN,
                      transform=ax_games.transAxes, ha="center", va="center")
        ax_games.text(0.5, 0.35, "days until 2026 kickoff",
                      fontsize=FONT_LABEL, color=DIM,
                      transform=ax_games.transAxes, ha="center", va="center")
        ax_games.text(0.5, 0.15, "Seahawks @ Patriots — Sept 9, 2026",
                      fontsize=FONT_SMALL, color=WHITE,
                      transform=ax_games.transAxes, ha="center", va="center")

    # ── RIGHT: SPORTSBOOK OPERATOR STOCKS ─────────────────────────────────────
    ax_bars.set_title("Sportsbook Stocks — 5-Day Return", fontsize=FONT_HEADLINE, color=DIM, pad=6)
    labels = [x[1] for x in valid]
    values = [x[3] for x in valid]
    bar_colors = [GREEN if v >= 0 else RED for v in values]

    if values:
        y_pos = range(len(labels))
        ax_bars.barh(list(y_pos), values, color=bar_colors, height=0.6, alpha=0.85)
        ax_bars.set_yticks(list(y_pos))
        ax_bars.set_yticklabels(labels, fontsize=FONT_LABEL, color=WHITE)
        ax_bars.tick_params(axis="x", labelsize=FONT_TINY, colors=DIM)
        ax_bars.axvline(0, color=GREY, linewidth=0.8, alpha=0.6)
        ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}%"))
        ax_bars.grid(axis="x", color=BORDER, linewidth=0.5, alpha=0.7)
        xmin, xmax = min(values), max(values) if max(values) > 0 else 0.5
        buf = (xmax - xmin) * 0.28 or 1.0
        ax_bars.set_xlim(xmin - buf, xmax + buf)
        for i, (v, c) in enumerate(zip(values, bar_colors)):
            off = (xmax - xmin) * 0.04 or 0.1
            ha = "left" if v >= 0 else "right"
            ax_bars.text(v + (off if v >= 0 else -off), i, f"{v:+.2f}%",
                         va="center", ha=ha, fontsize=FONT_TINY, color=c)
    else:
        ax_bars.axis("off")
        ax_bars.text(0.5, 0.5, "Stock data unavailable", fontsize=FONT_HEADLINE, color=GREY,
                     transform=ax_bars.transAxes, ha="center", va="center")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, FOOTER_Y, f"Source: ESPN · Yahoo Finance  |  Generated: {TIMESTAMP}",
             fontsize=FONT_SMALL, color=GREY, va="top")
    fig.text(MARGIN_RIGHT, FOOTER_Y, "@Mboya_Jeffers",
             fontsize=FONT_SMALL, color=CYAN, va="top", ha="right")
    fig.add_artist(plt.Line2D([MARGIN_LEFT, MARGIN_RIGHT], [FOOTER_LINE_Y, FOOTER_LINE_Y],
                              transform=fig.transFigure, color=BORDER, linewidth=0.8))

    detect_and_fix_overlaps(fig)
    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching NFL scoreboard...")
    games = fetch_nfl_scoreboard()

    print("Fetching sportsbook operator stocks...")
    stock_data = []
    for sym, name in OPERATORS:
        print(f"  {sym}...")
        p, r = fetch_5d(sym)
        stock_data.append((p, r))
        time.sleep(0.3)

    _, spy_ret = fetch_5d("SPY")

    print("Drawing card...")
    draw_card(games, stock_data, spy_ret)
    print("Done.")


if __name__ == "__main__":
    main()
