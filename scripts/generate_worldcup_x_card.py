#!/usr/bin/env python3
"""
FIFA World Cup 2026 — X Card Generator
Renderer: HTML/CSS → Chrome Headless → PNG

Fan Zone  (top ~58%): today's matches + group standings
Market Zone (bottom ~42%): sportsbook returns + key metrics
Output: REVENUE/X/cards/worldcup_x_card_YYYY-MM-DD.png (1200×675)
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf
from jinja2 import Environment, FileSystemLoader

from render_card import render_html_to_png, quality_check

try:
    from fetch_odds import fetch_wc_odds, inject_odds_into_matches
except ImportError:
    def fetch_wc_odds(*a, **kw): return []
    def inject_odds_into_matches(m, o): return m

# affiliate constants live in the bot folder
sys.path.insert(0, str(Path(__file__).parent.parent / "bot"))
try:
    from affiliate_config import CONTRA_BETTING_URL, BIO_LINK
except ImportError:
    CONTRA_BETTING_URL = "contra.com/mboya_jeffers"
    BIO_LINK           = "beacons.ai/mboyajeffers"

# Strip protocol prefix for display (e.g. "https://contra.com/..." → "contra.com/...")
_CONTRA_DISPLAY = CONTRA_BETTING_URL.lstrip("https://").lstrip("http://")
if _CONTRA_DISPLAY.startswith("["):  # still a placeholder
    _CONTRA_DISPLAY = "contra.com/mboya_jeffers"

# ─── PATHS ────────────────────────────────────────────────────────────────────

SCRIPTS_DIR   = Path(__file__).parent
TEMPLATES_DIR = SCRIPTS_DIR.parent / "templates"
OUT_DIR       = SCRIPTS_DIR.parent / "cards"
SCRATCHPAD    = Path("/tmp/cms_x_cards")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SCRATCHPAD.mkdir(parents=True, exist_ok=True)

_now_utc  = datetime.now(timezone.utc)
TODAY     = _now_utc.strftime("%Y-%m-%d")
TIMESTAMP = _now_utc.strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"worldcup_x_card_{TODAY}.png"

# ─── STAGE ────────────────────────────────────────────────────────────────────

FINAL_DATE = datetime(2026, 7, 19)


def get_stage():
    d = datetime.now().month * 100 + datetime.now().day
    if d <= 627: return "Group Stage"
    if d <= 704: return "Round of 32"
    if d <= 709: return "Round of 16"
    if d <= 713: return "Quarterfinals"
    if d <= 716: return "Semifinals"
    if d <= 719: return "Final — MetLife Stadium"
    return "Post-Tournament"


def days_to_final():
    return max(0, (FINAL_DATE - datetime.now()).days)


# ─── ESPN ─────────────────────────────────────────────────────────────────────

def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _parse_scoreboard(data):
    matches = []
    for event in data.get("events", []):
        comps       = event.get("competitions", [{}])[0]
        competitors = comps.get("competitors", [])
        if len(competitors) < 2:
            continue
        home    = competitors[0].get("team", {}).get("abbreviation", "???")[:3]
        away    = competitors[1].get("team", {}).get("abbreviation", "???")[:3]
        h_score = competitors[0].get("score", "")
        a_score = competitors[1].get("score", "")
        state   = event.get("status", {}).get("type", {}).get("state", "pre")
        detail  = event.get("status", {}).get("type", {}).get("shortDetail", "")
        try:
            dt_utc   = datetime.strptime(event.get("date", ""), "%Y-%m-%dT%H:%MZ")
            dt_et    = dt_utc.replace(tzinfo=timezone.utc) - timedelta(hours=4)
            time_str = dt_et.strftime("%-I:%M%p ET")
        except Exception:
            time_str = detail
        is_usa = home in ("USA", "US") or away in ("USA", "US")
        matches.append({"home": home, "away": away,
                        "h_score": h_score, "a_score": a_score,
                        "state": state, "time": time_str, "is_usa": is_usa})
    return matches


def fetch_today_matches():
    try:
        url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
               f"fifa.world/scoreboard?dates={datetime.now().strftime('%Y%m%d')}")
        return _parse_scoreboard(_fetch(url))
    except Exception as e:
        print(f"  ESPN today: {e}"); return []


def fetch_upcoming():
    for d in range(1, 6):
        try:
            dt      = datetime.now() + timedelta(days=d)
            url     = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
                       f"fifa.world/scoreboard?dates={dt.strftime('%Y%m%d')}")
            matches = _parse_scoreboard(_fetch(url))
            if matches:
                return matches, dt.strftime("%b %d")
        except Exception:
            continue
    return [], ""


def fetch_group_leaders():
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/standings"
    try:
        data   = _fetch(url)
        groups = []
        for group in data.get("standings", []):
            name = group.get("name", "")
            if not name.startswith("Group"):
                continue
            entries = group.get("standings", {}).get("entries", [])
            if len(entries) < 2:
                continue
            def _e(e):
                team = e.get("team", {}).get("abbreviation", "???")[:3]
                pts = w = d_ = losses = 0
                for s in e.get("stats", []):
                    sn = s.get("name", "")
                    if sn == "points": pts = int(s.get("value", 0))
                    elif sn == "wins":   w  = int(s.get("value", 0))
                    elif sn == "ties":  d_  = int(s.get("value", 0))
                    elif sn == "losses": losses = int(s.get("value", 0))
                return team, pts, f"{w}-{d_}-{losses}"
            t1, p1, r1 = _e(entries[0])
            t2, p2, r2 = _e(entries[1])
            groups.append({"group": name.replace("Group ", ""),
                           "t1": t1, "pts1": p1, "rec1": r1,
                           "t2": t2, "pts2": p2, "rec2": r2,
                           "tight": abs(p1 - p2) <= 2})
        return groups[:10]
    except Exception as e:
        print(f"  ESPN standings: {e}"); return []


def fetch_yesterday_results():
    try:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        url      = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
                    f"fifa.world/scoreboard?dates={date_str}")
        return [m for m in _parse_scoreboard(_fetch(url)) if m["state"] == "post"]
    except Exception:
        return []


# ─── MARKET DATA ──────────────────────────────────────────────────────────────

BASELINE_DATE = "2026-06-11"

SPORTSBOOK = [
    ("DKNG", "DraftKings"),
    ("FLUT", "Flutter/FanDuel"),
    ("PENN", "Penn Ent."),
    ("MGM",  "MGM Resorts"),
    ("BETZ", "BETZ ETF"),
]


def wc_return(ticker, retries=3):
    for i in range(retries):
        try:
            hist = yf.Ticker(ticker).history(start=BASELINE_DATE)
            if hist.empty or len(hist) < 2:
                raise ValueError("no data")
            c = hist["Close"].dropna().tolist()
            return round(c[-1], 2), round((c[-1] - c[0]) / c[0] * 100, 2)
        except Exception:
            if i < retries - 1: time.sleep(2)
    return None, None


# ─── RENDER ───────────────────────────────────────────────────────────────────

def build_bar_data(sb_data):
    """Convert raw sportsbook data into bar chart context: sorted desc, pct widths."""
    valid = [(sym, name, p, r)
             for (sym, name), (p, r) in zip(SPORTSBOOK, sb_data)
             if r is not None]
    if not valid:
        return []
    valid_sorted = sorted(valid, key=lambda x: x[3], reverse=True)
    max_abs = max(abs(x[3]) for x in valid_sorted) or 1.0
    bars = []
    for sym, name, price, ret in valid_sorted:
        pct = round(abs(ret) / max_abs * 100, 1)
        bars.append({
            "name":  name,
            "pct":   pct,
            "pos":   ret >= 0,
            "label": f"{ret:+.1f}%",
        })
    return bars


def build_stat_rows(sb_data, spy_ret, top_ml_match=None):
    """Build stat rows for the Market Pulse panel."""
    valid = [(sym, name, p, r)
             for (sym, name), (p, r) in zip(SPORTSBOOK, sb_data)
             if r is not None]
    spy_r = spy_ret or 0.0

    rows = []
    dkng_ret = next((r for (sym, _), (p, r) in zip(SPORTSBOOK, sb_data)
                     if sym == "DKNG" and r is not None), None)
    if dkng_ret is not None:
        rows.append({"label": "DKNG since Jun 11",
                     "value": f"{dkng_ret:+.1f}%",
                     "cls":   "pos" if dkng_ret >= 0 else "neg"})
    if valid:
        avg = sum(x[3] for x in valid) / len(valid)
        rows.append({"label": "Sector avg (5 ops)",
                     "value": f"{avg:+.1f}%",
                     "cls":   "pos" if avg >= 0 else "neg"})
    if spy_ret is not None:
        rows.append({"label": "SPY since Jun 11",
                     "value": f"{spy_r:+.1f}%",
                     "cls":   "pos" if spy_r >= 0 else "neg"})

    rows.append({"divider": True})

    # Live odds row: top match ML (or AGA handle if no odds available)
    if top_ml_match and top_ml_match.get("ml_home") is not None:
        ml_h = top_ml_match["ml_home"]
        ml_a = top_ml_match["ml_away"]
        label = f"{top_ml_match['home']} vs {top_ml_match['away']} (DK)"
        value = f"{ml_h:+d} / {ml_a:+d}"
        rows.append({"label": label, "value": value, "cls": "gold"})
    else:
        rows.append({"label": "US Handle (proj.)", "value": "$4.3B (AGA 2026)", "cls": "brand"})

    rows.append({"label": "vs Qatar 2022", "value": "3× growth", "cls": "brand"})
    return rows


def build_subhead(sb_data, spy_ret, days_left, today_matches=None):
    """Fan hook first, bettor signal embedded — not a financial ticker."""
    valid = [(sym, name, p, r)
             for (sym, name), (p, r) in zip(SPORTSBOOK, sb_data)
             if r is not None]
    spy_r  = spy_ret or 0.0
    avg    = sum(x[3] for x in valid) / len(valid) if valid else 0.0
    top    = max(valid, key=lambda x: x[3]) if valid else None

    # Check if USA is playing today
    usa_match = None
    if today_matches:
        usa_match = next((m for m in today_matches if m.get("is_usa")), None)

    if usa_match:
        ml_note = ""
        if usa_match.get("ml_home") is not None:
            usa_is_home = usa_match.get("home", "") in ("USA", "US")
            usa_ml = usa_match["ml_home"] if usa_is_home else usa_match["ml_away"]
            ml_note = f"· USA {usa_ml:+d}"
        market_note = f"· Sportsbooks avg {avg:+.1f}% since kickoff" if valid else ""
        parts = ["★ USA playing TODAY", usa_match["time"]]
        if ml_note:
            parts.append(ml_note)
        if market_note:
            parts.append(market_note)
        parts.append(f"· {days_left}d to Final")
        return "  ".join(parts)

    if today_matches:
        # Show most interesting non-USA match
        m = today_matches[0]
        market_note = f"· Sportsbooks {avg:+.1f}% since Jun 11" if valid else ""
        return f"{m['home']} vs {m['away']} today  {market_note}  · {days_left}d to Final"

    # No matches today — lead with market signal
    if top and avg > spy_r + 2:
        return (f"Sportsbooks avg {avg:+.1f}% since Jun 11 kickoff  ·  "
                f"outpacing S&P by {avg - spy_r:.1f}pp  ·  {days_left}d to Final")
    elif top:
        return (f"{top[1]} leads operators at {top[3]:+.1f}%  ·  "
                f"Sector avg {avg:+.1f}%  vs  SPY {spy_r:+.1f}%  ·  {days_left}d to Final")
    return f"$4.3B projected US handle  ·  {days_left} days to MetLife Final"


def render_card(sb_data, spy_ret,
                today_matches, upcoming_matches, upcoming_label,
                group_leaders, yesterday_results,
                odds_source=""):

    stage     = get_stage()
    days_left = days_to_final()

    # Resolve match list + label
    if today_matches:
        show_matches  = today_matches
        matches_label = "Today's Matches"
    elif upcoming_matches:
        show_matches  = upcoming_matches
        matches_label = f"Upcoming  ·  {upcoming_label}"
    elif yesterday_results:
        show_matches  = yesterday_results
        matches_label = "Yesterday's Results"
    else:
        show_matches  = []
        matches_label = "Match Data"

    sorted_m = sorted(show_matches, key=lambda m: (not m["is_usa"], m["time"]))[:5]

    # Find the most prominent pre-game match for odds display in stats panel
    top_ml_match = next(
        (m for m in sorted_m if m.get("state") == "pre" and m.get("ml_home") is not None),
        None
    )

    if group_leaders:
        standings_label = "Group Leaders"
    elif yesterday_results:
        standings_label = "Yesterday's Results"
    else:
        standings_label = "Tournament"

    ctx = {
        "stage":           stage,
        "date":            datetime.now().strftime("%b %d, %Y"),
        "subhead":         build_subhead(sb_data, spy_ret, days_left, today_matches),
        "timestamp":       TIMESTAMP,
        "days_left":       days_left,
        "matches_label":   matches_label,
        "matches":         sorted_m,
        "standings_label": standings_label,
        "groups":          group_leaders if group_leaders else [],
        "yesterday":       yesterday_results[:5] if not group_leaders else [],
        "bars":            build_bar_data(sb_data),
        "stats":           build_stat_rows(sb_data, spy_ret, top_ml_match=top_ml_match),
        "contra_url":      _CONTRA_DISPLAY,
        "bio_link":        BIO_LINK,
        "odds_source":     odds_source,
    }

    env      = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("worldcup_card.html")
    html     = template.render(**ctx)

    tmp_html = SCRATCHPAD / f"worldcup_card_{TODAY}.html"
    tmp_html.write_text(html, encoding="utf-8")

    print(f"  Rendering via Chrome headless → {OUT_PATH}")
    render_html_to_png(tmp_html, OUT_PATH)
    print("  Running quality check...")
    quality_check(OUT_PATH)
    print(f"  Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching sportsbook data (since Jun 11)...")
    sb_data = []
    for sym, name in SPORTSBOOK:
        print(f"  {sym}...")
        p, r = wc_return(sym)
        sb_data.append((p, r))
        time.sleep(0.3)

    print("Fetching SPY...")
    _, spy_ret = wc_return("SPY")

    print("Fetching today's matches (ESPN)...")
    today_matches = fetch_today_matches()
    print(f"  {len(today_matches)} today")

    upcoming_matches, upcoming_label = [], ""
    if not today_matches:
        print("Fetching upcoming...")
        upcoming_matches, upcoming_label = fetch_upcoming()

    print("Fetching group standings...")
    group_leaders = fetch_group_leaders()
    print(f"  {len(group_leaders)} groups")

    yesterday_results = []
    if not group_leaders:
        print("Fetching yesterday results (fallback)...")
        yesterday_results = fetch_yesterday_results()
        print(f"  {len(yesterday_results)} results")

    # Fetch live odds (requires ODDS_API_KEY — silent no-op if absent)
    odds_source = ""
    api_key = os.environ.get("ODDS_API_KEY", "")
    if api_key:
        print("Fetching WC match odds (The Odds API)...")
        odds = fetch_wc_odds(api_key)
        print(f"  {len(odds)} matches with odds")
        if odds:
            today_matches    = inject_odds_into_matches(today_matches, odds)
            upcoming_matches = inject_odds_into_matches(upcoming_matches, odds)
            odds_source = "The Odds API"
    else:
        print("  ODDS_API_KEY not set — skipping live odds (add to ~/.x_bot_env)")

    print("Rendering card...")
    render_card(sb_data, spy_ret,
                today_matches, upcoming_matches, upcoming_label,
                group_leaders, yesterday_results,
                odds_source=odds_source)
    print("Done.")


if __name__ == "__main__":
    main()
