#!/usr/bin/env python3
"""
Insight post engine — text-only, trend-aware posts for @Mboya_Jeffers.

Pipeline:
  fetch_google_news()       → recent headlines per domain
  fetch_domain_data()       → live data snapshot (reuses post.py helpers)
  detect_notable_signal()   → picks the strongest single signal
  build_context_string()    → formats context for Claude
  call_claude()             → generates human-voiced caption (≤270 chars)
  build_caption_insight()   → top-level entry point (called by CAPTION_BUILDERS)
"""

import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BOT_DIR))

# ─── VOICE PROMPT ─────────────────────────────────────────────────────────────

VOICE_SYSTEM_PROMPT = """You are Mboya Jeffers, a data engineer who posts market + sports analytics on X (@Mboya_Jeffers).
Write exactly 1 tweet (max 270 chars). Use the data provided. Be specific: real numbers, real names.
Voice: direct, honest, present-tense — like a credible journalist's quick take, not a fan and not an AI.
On sports: celebrate the game and the result. Congratulate the winning team by name. Neutral on team allegiances — your loyalty is to accuracy and the sport itself, never to an outcome.
On markets: report what happened without cheerleading or panic. Let the numbers speak.
FORBIDDEN: "it's worth noting", "interestingly", "dive into", "let that sink in", "game-changing", "buckle up", "in conclusion", "importantly", "as of today", "navigate", em-dashes (—), exclamation marks.
No hashtags. No trailing CTAs. No "Follow me". Return ONLY the tweet text, nothing else."""

# All-Star Game date — used for baseball signal scoring
_ALLSTAR_DATE = datetime(2026, 7, 14)

# Marquee MLB teams for featured-game detection
_MLB_MARQUEE = {"NYY", "LAD", "NYM", "BOS", "HOU", "TEX", "ATL", "SF"}

# News queries per domain
NEWS_QUERIES = {
    "crypto":   "bitcoin crypto market",
    "markets":  "stock market SPY VIX",
    "worldcup": "FIFA World Cup 2026",
    "baseball": "MLB baseball All-Star 2026",
}

# ─── NEWS FETCH ───────────────────────────────────────────────────────────────

def fetch_google_news(query, max_results=4):
    """Pull recent headlines from Google News RSS. Returns list of title strings."""
    url = (
        f"https://news.google.com/rss/search"
        f"?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            root = ET.fromstring(r.read())
        items = root.findall(".//item")[:max_results]
        headlines = []
        for item in items:
            t = item.find("title")
            if t is not None and t.text:
                # Strip " - Source Name" suffix Google appends
                title = t.text.rsplit(" - ", 1)[0].strip()
                headlines.append(title)
        return headlines
    except Exception as e:
        print(f"  [news] {query!r} fetch failed: {e}")
        return []


def fetch_all_headlines():
    """Returns dict of domain → [headline, ...]."""
    return {domain: fetch_google_news(query) for domain, query in NEWS_QUERIES.items()}

# ─── MLB HELPER ───────────────────────────────────────────────────────────────

def _fetch_mlb_today():
    """Fetch today's MLB games from ESPN scoreboard API."""
    today_str = datetime.now().strftime("%Y%m%d")
    url = (f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/"
           f"scoreboard?dates={today_str}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        games = []
        for event in data.get("events", []):
            comps = event.get("competitions", [{}])[0]
            teams = comps.get("competitors", [])
            if len(teams) < 2:
                continue
            home = teams[0].get("team", {}).get("abbreviation", "???")
            away = teams[1].get("team", {}).get("abbreviation", "???")
            h_score = teams[0].get("score", "")
            a_score = teams[1].get("score", "")
            state   = event.get("status", {}).get("type", {}).get("state", "pre")
            detail  = event.get("status", {}).get("type", {}).get("shortDetail", "")
            games.append({
                "home": home, "away": away,
                "h_score": h_score, "a_score": a_score,
                "state": state, "detail": detail,
                "marquee": any(t in _MLB_MARQUEE for t in (home, away)),
            })
        return games
    except Exception as e:
        print(f"  [mlb] scoreboard fetch failed: {e}")
        return []


# ─── DATA SNAPSHOT ────────────────────────────────────────────────────────────

def fetch_domain_data():
    """
    Lightweight live-data snapshot across all insight domains.
    Imports helpers from post.py (already imported at bot level).
    Returns a flat dict of named signals.
    """
    from post import (
        _yf_5d, _coingecko, _fear_greed,
        _fetch_wc_today, _fetch_wc_yesterday,
    )

    data = {}

    # ── Markets ───────────────────────────────────────────────────────────────
    try:
        spy_price, spy_5d = _yf_5d("SPY")
        data["spy_price"] = spy_price
        data["spy_5d"]    = spy_5d
    except Exception:
        pass

    try:
        vix, _ = _yf_5d("^VIX")
        data["vix"] = vix
    except Exception:
        pass

    # ── Crypto ────────────────────────────────────────────────────────────────
    try:
        markets = _coingecko(
            "/coins/markets?vs_currency=usd&order=market_cap_desc"
            "&per_page=5&page=1&sparkline=false&price_change_percentage=24h,7d"
        )
        if markets:
            btc = next((m for m in markets if m["symbol"] == "btc"), None)
            eth = next((m for m in markets if m["symbol"] == "eth"), None)
            if btc:
                data["btc_price"] = btc["current_price"]
                data["btc_24h"]   = btc.get("price_change_percentage_24h_in_currency")
                data["btc_7d"]    = btc.get("price_change_percentage_7d_in_currency")
            if eth:
                data["eth_24h"] = eth.get("price_change_percentage_24h_in_currency")
    except Exception:
        pass

    try:
        gd = _coingecko("/global")
        if gd and "data" in gd:
            data["btc_dom"] = gd["data"]["market_cap_percentage"].get("btc")
            total = gd["data"]["total_market_cap"].get("usd")
            data["total_mcap_t"] = total / 1e12 if total else None
    except Exception:
        pass

    try:
        fg_val, fg_label = _fear_greed()
        data["fg_value"] = fg_val
        data["fg_label"] = fg_label
    except Exception:
        pass

    # ── World Cup ─────────────────────────────────────────────────────────────
    try:
        today     = _fetch_wc_today()
        yesterday = _fetch_wc_yesterday()
        data["wc_today"]     = today
        data["wc_yesterday"] = yesterday
    except Exception:
        data["wc_today"]     = []
        data["wc_yesterday"] = []

    # ── Baseball ──────────────────────────────────────────────────────────────
    try:
        data["mlb_today"]          = _fetch_mlb_today()
        data["mlb_days_to_allstar"] = max(0, (_ALLSTAR_DATE - datetime.now()).days)
    except Exception:
        data["mlb_today"]          = []
        data["mlb_days_to_allstar"] = None

    return data

# ─── SIGNAL DETECTION ─────────────────────────────────────────────────────────

def _wc_finished(matches):
    return [m for m in matches if m.get("state") == "post"]


def _wc_upcoming(matches):
    return [m for m in matches if m.get("state") == "pre"]


def detect_notable_signal(data):
    """
    Score each domain and return the highest-value signal.
    Returns (domain, score, signal_dict) — caller builds context from signal_dict.
    """
    signals = []

    # ── WC: finished matches (highest priority when results are available) ────
    yest_ft  = _wc_finished(data.get("wc_yesterday", []))
    today_ft = _wc_finished(data.get("wc_today",     []))
    finished = today_ft or yest_ft
    if finished:
        has_usa = any(m["is_usa"] for m in finished)
        score   = 4 + (1 if has_usa else 0)
        signals.append(("worldcup_results", score, {
            "matches": finished,
            "has_usa": has_usa,
        }))

    # ── WC: upcoming today ────────────────────────────────────────────────────
    upcoming = _wc_upcoming(data.get("wc_today", []))
    if upcoming:
        has_usa = any(m["is_usa"] for m in upcoming)
        score   = 3 if has_usa else 2
        signals.append(("worldcup_upcoming", score, {
            "matches": upcoming,
            "has_usa": has_usa,
        }))

    # ── Baseball — DISABLED 2026-08-11 ──────────────────────────────────────
    # Two problems found live: (1) mlb_days_to_allstar was clamped with max(0, ...),
    # so once the hardcoded _ALLSTAR_DATE (Jul 14 2026) passed, the "days until"
    # value permanently reads 0 and this signal fires at max priority forever —
    # produced a stale "MLB All-Star Game is today" draft a month after the fact.
    # (2) build_context_string()'s baseball branch has hardcoded roster/date text
    # ("Ohtani led all vote-getters", "MLB — July 10, 2026"), not live-fetched —
    # contradicts the live-data claim this account is built on. Not part of the
    # finance/crypto/data-engineering wedge either. Disabled rather than patched;
    # crypto/markets/worldcup below always provide a live, accurate fallback.

    # ── Crypto ────────────────────────────────────────────────────────────────
    btc_24h = data.get("btc_24h")
    fg_val  = data.get("fg_value")
    btc_dom = data.get("btc_dom")
    if btc_24h is not None and abs(btc_24h) >= 4:
        signals.append(("crypto_move", 3, {
            "btc_price": data.get("btc_price"),
            "btc_24h":   btc_24h,
            "eth_24h":   data.get("eth_24h"),
            "fg_value":  fg_val,
            "fg_label":  data.get("fg_label"),
        }))
    elif fg_val is not None and (fg_val <= 20 or fg_val >= 80):
        signals.append(("crypto_sentiment", 2, {
            "fg_value": fg_val,
            "fg_label": data.get("fg_label"),
            "btc_dom":  btc_dom,
        }))
    elif btc_dom is not None and btc_dom > 58:
        signals.append(("crypto_dominance", 1, {
            "btc_dom":       btc_dom,
            "total_mcap_t":  data.get("total_mcap_t"),
        }))

    # ── Markets ───────────────────────────────────────────────────────────────
    vix     = data.get("vix")
    spy_5d  = data.get("spy_5d")
    if vix is not None and vix > 25:
        signals.append(("market_vix", 3, {"vix": vix, "spy_5d": spy_5d}))
    elif spy_5d is not None and abs(spy_5d) > 3:
        signals.append(("market_spy", 2, {"spy_5d": spy_5d, "spy_price": data.get("spy_price"), "vix": vix}))
    else:
        score = 1 if (spy_5d is not None or vix is not None) else 0
        if score:
            signals.append(("market_general", score, {
                "spy_5d": spy_5d, "spy_price": data.get("spy_price"), "vix": vix,
            }))

    if not signals:
        # Fallback: use whatever we have
        signals.append(("market_general", 0, {
            "spy_5d": data.get("spy_5d"), "vix": data.get("vix"),
        }))

    # Highest score wins; within same score, keep insertion order (WC > crypto > markets)
    signals.sort(key=lambda s: s[1], reverse=True)
    return signals[0]

# ─── CONTEXT BUILDER ──────────────────────────────────────────────────────────

def build_context_string(domain, signal_dict, headlines):
    """
    Format the signal + relevant headlines into a compact context string for Claude.
    """
    lines = []

    if domain == "worldcup_results":
        matches = signal_dict["matches"][:4]
        lines.append("World Cup 2026 results:")
        for m in matches:
            lines.append(f"  {m['home']} {m['h_score']}-{m['a_score']} {m['away']} (FT)")
        if signal_dict.get("has_usa"):
            usa = next((m for m in matches if m["is_usa"]), None)
            if usa:
                lines.append(f"USA involved: {usa['home']} vs {usa['away']}")

    elif domain == "worldcup_upcoming":
        matches = signal_dict["matches"][:3]
        lines.append("World Cup 2026 — matches today:")
        for m in matches:
            lines.append(f"  {m['home']} vs {m['away']}  {m['time']}")
        if signal_dict.get("has_usa"):
            lines.append("USA is playing today.")

    elif domain == "crypto_move":
        btc_24h = signal_dict.get("btc_24h")
        eth_24h = signal_dict.get("eth_24h")
        lines.append(f"Bitcoin 24h change: {btc_24h:+.1f}%" if btc_24h is not None else "")
        if eth_24h is not None:
            lines.append(f"Ethereum 24h change: {eth_24h:+.1f}%")
        if signal_dict.get("btc_price"):
            lines.append(f"BTC price: ${signal_dict['btc_price']:,.0f}")
        fg = signal_dict.get("fg_value")
        if fg is not None:
            lines.append(f"Fear & Greed index: {fg} ({signal_dict.get('fg_label', '')})")

    elif domain == "crypto_sentiment":
        fg = signal_dict.get("fg_value")
        lines.append(f"Fear & Greed index: {fg} ({signal_dict.get('fg_label', '')})")
        if signal_dict.get("btc_dom"):
            lines.append(f"BTC dominance: {signal_dict['btc_dom']:.1f}%")

    elif domain == "crypto_dominance":
        lines.append(f"BTC dominance: {signal_dict['btc_dom']:.1f}%")
        if signal_dict.get("total_mcap_t"):
            lines.append(f"Total crypto market cap: ${signal_dict['total_mcap_t']:.2f}T")

    elif domain == "market_vix":
        lines.append(f"VIX: {signal_dict['vix']:.1f} (elevated volatility)")
        if signal_dict.get("spy_5d") is not None:
            lines.append(f"SPY 5-day return: {signal_dict['spy_5d']:+.1f}%")

    elif domain in ("market_spy", "market_general"):
        if signal_dict.get("spy_5d") is not None:
            lines.append(f"SPY 5-day return: {signal_dict['spy_5d']:+.1f}%")
        if signal_dict.get("spy_price"):
            lines.append(f"SPY price: ${signal_dict['spy_price']:.2f}")
        if signal_dict.get("vix") is not None:
            lines.append(f"VIX: {signal_dict['vix']:.1f}")

    elif domain in ("baseball_allstar", "baseball_games"):
        days    = signal_dict.get("days_to_allstar")
        games   = signal_dict.get("games", [])
        marquee = signal_dict.get("marquee") or [g for g in games if g.get("marquee")][:3]

        lines.append("MLB — July 10, 2026")

        if days is not None and days <= 5:
            label = "today" if days == 0 else (f"{days} day away" if days == 1 else f"{days} days away")
            lines.append(f"All-Star Game: {label} (Jul 14, 2026)")
            lines.append("All-Star starters voted in: Ohtani (LAD) led all vote-getters")
            lines.append("Yankees send: Judge, Ben Rice (breakout year), Bellinger, Schlittler")
            lines.append("Dodgers send 4 starters total (Ohtani + Freeman + 2 more)")

        finished = [g for g in games if g["state"] == "post"]
        live     = [g for g in games if g["state"] == "in"]
        pre      = [g for g in games if g["state"] == "pre"]

        if finished:
            lines.append("Final scores:")
            for g in finished[:3]:
                lines.append(f"  {g['away']} {g['a_score']} @ {g['home']} {g['h_score']} (F)")
        if live:
            lines.append("In progress:")
            for g in live[:3]:
                lines.append(f"  {g['away']} {g['a_score']} @ {g['home']} {g['h_score']} ({g['detail']})")
        if pre:
            show = marquee if marquee else pre[:4]
            lines.append("Tonight's games:")
            for g in show[:4]:
                lines.append(f"  {g['away']} @ {g['home']}  {g['detail']}")

    context = "\n".join(ln for ln in lines if ln.strip())

    # Append relevant headlines as additional context
    if headlines:
        context += "\n\nRecent headlines:\n" + "\n".join(f"- {h}" for h in headlines[:3])

    return context

# ─── CLAUDE API ───────────────────────────────────────────────────────────────

def call_claude_cli(context):
    """
    Generate tweet text by piping a prompt into the local `claude` CLI.
    Uses the active Claude Code session — no API key or billing required.
    """
    import subprocess

    prompt = f"{VOICE_SYSTEM_PROMPT}\n\nData:\n{context}"

    # Strip ANTHROPIC_API_KEY so claude CLI uses the claude.ai session login,
    # not the API account (which may have no credits).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    result = subprocess.run(
        ["claude", "--print"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}): {result.stderr.strip()[:200]}"
        )

    return result.stdout.strip()

# ─── MAIN ENTRY POINT ─────────────────────────────────────────────────────────

def build_caption_insight():
    """
    Top-level caption builder for the 'insight' vertical.
    Called by CAPTION_BUILDERS in post.py via xbot preview.
    Returns a ≤270-char text-only caption (no card).
    """
    print("  Fetching news headlines...")
    all_headlines = fetch_all_headlines()

    print("  Fetching live data snapshot...")
    data = fetch_domain_data()

    print("  Detecting notable signal...")
    domain, score, signal_dict = detect_notable_signal(data)
    print(f"  Signal: {domain} (score {score})")

    # Map domain to which headlines are most relevant
    headline_map = {
        "worldcup_results":  all_headlines.get("worldcup", []),
        "worldcup_upcoming": all_headlines.get("worldcup", []),
        "crypto_move":       all_headlines.get("crypto", []),
        "crypto_sentiment":  all_headlines.get("crypto", []),
        "crypto_dominance":  all_headlines.get("crypto", []),
        "market_vix":        all_headlines.get("markets", []),
        "market_spy":        all_headlines.get("markets", []),
        "market_general":    all_headlines.get("markets", []),
        "baseball_allstar":  all_headlines.get("baseball", []),
        "baseball_games":    all_headlines.get("baseball", []),
    }
    headlines = headline_map.get(domain, [])

    context = build_context_string(domain, signal_dict, headlines)
    print(f"  Calling Claude... (context: {len(context)} chars)")

    draft = call_claude_cli(context)

    # Hard cap — never exceed X's limit
    return draft[:270]
