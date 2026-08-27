#!/usr/bin/env python3
"""
Insight post engine — text-only, trend-aware posts for @Mboya_Jeffers.

Vertical-specific as of 2026-08-26 (see REVENUE/X/strategy/AUDIENCE_TRUST_STRATEGY.md) —
each domain has its own persona-appropriate voice add-on and its own real data source, not one
generic "market commentary" voice covering unrelated verticals. Only domains with a real, live,
free data source already proven elsewhere in this codebase are implemented — no fabricated
specifics (no invented odds/lines/bonus terms) for domains that lack one (see the strategy doc's
Build Status section for what's deliberately not built yet, and why).

Pipeline:
  fetch_google_news()       → recent headlines per domain
  fetch_domain_data()       → live data snapshot (reuses post.py + card-generator patterns)
  detect_notable_signal()   → picks the strongest single signal across all wired domains
  build_context_string()    → formats context for Claude
  call_claude()             → generates human-voiced caption (≤270 chars), voice tailored per domain
  build_caption_insight()   → top-level entry point (called by CAPTION_BUILDERS)
"""

import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BOT_DIR))

# ─── VOICE PROMPT ─────────────────────────────────────────────────────────────

VOICE_SYSTEM_PROMPT_BASE = """You are Mboya Jeffers, a data engineer who posts market + sector analytics on X (@Mboya_Jeffers).
Write exactly 1 tweet (max 270 chars). Use ONLY the data and headlines given below. Be specific: real numbers, real names.
Voice: direct, honest, present-tense — like a credible journalist's quick take, not a fan and not an AI.
On markets: report what happened without cheerleading or panic. Let the numbers speak.
CRITICAL — do not invent causes: never state or imply a reason, cause, or news event behind a move
unless it is explicitly present in the "Recent headlines" section below. If no headlines are given,
or none explain the move, report the numbers only — do not guess at geopolitics, earnings, Fed
action, or any other cause. An invented reason is worse than no reason.
FORBIDDEN: "it's worth noting", "interestingly", "dive into", "let that sink in", "game-changing", "buckle up", "in conclusion", "importantly", "as of today", "navigate", em-dashes (—), exclamation marks.
No hashtags. No trailing CTAs. No "Follow me". Return ONLY the tweet text, nothing else."""

# Per-domain voice add-ons — appended to the base prompt. Each one encodes what that
# specific audience actually trusts (see the per-vertical breakdown in the strategy doc),
# not a one-size-fits-all tone.
VOICE_ADDONS = {
    "crypto_move":       "\nOn crypto: no hype language, no \"moon\"/\"degen\" framing. Report the move and cite Fear & Greed honestly even if it undercuts a bullish read.",
    "crypto_sentiment":  "\nOn crypto: no hype language. Sentiment extremes (Fear & Greed) are the story here — say what the reading actually implies without predicting price.",
    "crypto_dominance":  "\nOn crypto: no hype language. Dominance shifts are a capital-rotation signal, not a verdict on any one coin.",
    "market_vix":        "\nAudience is retail investors. No \"guaranteed\" framing, no fear-mongering about volatility — report the level and what it typically means.",
    "market_spy":        "\nAudience is retail investors. Report the move plainly, cite the real timeframe, no cherry-picked framing.",
    "market_general":    "\nAudience is retail investors. Report the move plainly, cite the real timeframe, no cherry-picked framing.",
    "oilgas_move":       "\nAudience is energy-sector-interested investors/professionals. Straight production/price data (WTI, Henry Hub) — zero political framing either direction, cite FRED as the source.",
    "brokerage_options": "\nAudience is retail investors evaluating where to hold money. Report options positioning (put/call ratio) as market structure, not a trade signal — never imply this is investment advice.",
    "betting_business":  "\nThis is sportsbook-INDUSTRY commentary (operator stock performance, market data) for people interested in the betting business — NOT betting picks, NOT odds, NOT predictions on any game or line. Never use words like \"bet,\" \"pick,\" \"lock,\" or \"play\" in the sense of a wager. If it could be read as betting advice, don't write it.",
}

# All-Star Game date — used for baseball signal scoring
_ALLSTAR_DATE = datetime(2026, 7, 14)

# Marquee MLB teams for featured-game detection
_MLB_MARQUEE = {"NYY", "LAD", "NYM", "BOS", "HOU", "TEX", "ATL", "SF"}

# News queries per domain
NEWS_QUERIES = {
    "crypto":     "bitcoin crypto market",
    "markets":    "stock market SPY VIX",
    "baseball":   "MLB baseball All-Star 2026",
    "oilgas":     "crude oil natural gas price",
    "brokerage":  "stock market options volatility",
    "betting":    "DraftKings FanDuel sportsbook",
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


# ─── NEW DOMAIN FETCHERS (2026-08-26) ──────────────────────────────────────────
# Same patterns already proven in the respective card generators
# (generate_oilgas_x_card.py, generate_brokerage_x_card.py, generate_betting_x_card.py) —
# reused here rather than re-derived, and kept keyless (FRED's CSV endpoint and
# yfinance both work without an API key for these series).

def _fetch_fred_series(series_id, start="2025-01-01", max_retries=3):
    """Returns (latest_val, pct_chg_vs_prior) or (None, None) on failure."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "15", url],
                capture_output=True, text=True, timeout=20,
            )
            if not result.stdout.strip():
                raise RuntimeError("empty FRED response")
            reader = csv.reader(io.StringIO(result.stdout))
            next(reader)
            rows = [(r[0], float(r[1])) for r in reader
                    if len(r) >= 2 and r[1] and r[1] not in (".", "")]
            if len(rows) < 2:
                raise RuntimeError("insufficient FRED rows")
            latest_val, prev_val = rows[-1][1], rows[-2][1]
            chg = (latest_val - prev_val) / prev_val * 100
            return round(latest_val, 2), round(chg, 2)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return None, None


def _fetch_options_pcr(ticker="SPY", max_retries=3):
    """Put/call volume ratio from the nearest expiration. Returns dict or None."""
    for attempt in range(max_retries):
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            exps = t.options
            if not exps:
                return None
            chain = t.option_chain(exps[0])
            call_vol = int(chain.calls["volume"].fillna(0).sum())
            put_vol = int(chain.puts["volume"].fillna(0).sum())
            if call_vol == 0:
                return None
            return {"calls": call_vol, "puts": put_vol, "pcr": round(put_vol / call_vol, 2)}
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return None


# ─── DATA SNAPSHOT ────────────────────────────────────────────────────────────

def fetch_domain_data():
    """
    Lightweight live-data snapshot across all insight domains.
    Imports helpers from post.py (already imported at bot level).
    Returns a flat dict of named signals.
    """
    from post import _yf_5d, _coingecko, _fear_greed

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

    # ── Oil & Gas (WTI + Henry Hub, same series as the oilgas card) ─────────────
    try:
        data["wti_price"], data["wti_chg"] = _fetch_fred_series("DCOILWTICO")
        data["ng_price"], data["ng_chg"]   = _fetch_fred_series("MHHNGSP")
    except Exception:
        pass

    # ── Brokerage (SPY options positioning + VIX, same pattern as brokerage card) ─
    try:
        data["spy_pcr"] = _fetch_options_pcr("SPY")
    except Exception:
        data["spy_pcr"] = None

    # ── Betting (sportsbook operator stocks — see VOICE_ADDONS: never framed as picks) ─
    try:
        dknq_price, dknq_5d = _yf_5d("DKNG")
        flut_price, flut_5d = _yf_5d("FLUT")
        data["dknq_price"], data["dknq_5d"] = dknq_price, dknq_5d
        data["flut_price"], data["flut_5d"] = flut_price, flut_5d
    except Exception:
        pass

    # ── Baseball ──────────────────────────────────────────────────────────────
    try:
        data["mlb_today"]          = _fetch_mlb_today()
        data["mlb_days_to_allstar"] = max(0, (_ALLSTAR_DATE - datetime.now()).days)
    except Exception:
        data["mlb_today"]          = []
        data["mlb_days_to_allstar"] = None

    return data

# ─── SIGNAL DETECTION ─────────────────────────────────────────────────────────

def detect_notable_signal(data):
    """
    Score each domain and return the highest-value signal.
    Returns (domain, score, signal_dict) — caller builds context from signal_dict.
    """
    signals = []

    # World Cup signal removed 2026-08-26 — the worldcup vertical itself was
    # retired the same day (tournament ended 2026-07-19, replaced by nfl in
    # post.py), so a live worldcup insight branch here was dead code pointing
    # at data fetchers (_fetch_wc_today/_fetch_wc_yesterday) that no longer
    # get called. NFL isn't a drop-in replacement: no real live NFL data
    # source is wired here yet (season starts 2026-09-09) — see the strategy
    # doc's Build Status for what's scoped but not built.

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

    # ── Oil & Gas ─────────────────────────────────────────────────────────────
    wti_chg = data.get("wti_chg")
    ng_chg  = data.get("ng_chg")
    if wti_chg is not None and abs(wti_chg) >= 2:
        signals.append(("oilgas_move", 3, {
            "wti_price": data.get("wti_price"), "wti_chg": wti_chg,
            "ng_price": data.get("ng_price"), "ng_chg": ng_chg,
        }))
    elif ng_chg is not None and abs(ng_chg) >= 5:
        signals.append(("oilgas_move", 2, {
            "wti_price": data.get("wti_price"), "wti_chg": wti_chg,
            "ng_price": data.get("ng_price"), "ng_chg": ng_chg,
        }))

    # ── Brokerage (options positioning) ─────────────────────────────────────────
    pcr = data.get("spy_pcr")
    if pcr and pcr.get("pcr") is not None and (pcr["pcr"] >= 1.2 or pcr["pcr"] <= 0.6):
        signals.append(("brokerage_options", 2, {"pcr": pcr, "vix": data.get("vix")}))

    # ── Betting (sportsbook operator stocks) ────────────────────────────────────
    dknq_5d = data.get("dknq_5d")
    flut_5d = data.get("flut_5d")
    if (dknq_5d is not None and abs(dknq_5d) >= 5) or (flut_5d is not None and abs(flut_5d) >= 5):
        signals.append(("betting_business", 2, {
            "dknq_price": data.get("dknq_price"), "dknq_5d": dknq_5d,
            "flut_price": data.get("flut_price"), "flut_5d": flut_5d,
        }))

    if not signals:
        # Fallback: use whatever we have
        signals.append(("market_general", 0, {
            "spy_5d": data.get("spy_5d"), "vix": data.get("vix"),
        }))

    # Highest score wins; within same score, keep insertion order (crypto > markets > oilgas > brokerage > betting)
    signals.sort(key=lambda s: s[1], reverse=True)
    return signals[0]

# ─── CONTEXT BUILDER ──────────────────────────────────────────────────────────

def build_context_string(domain, signal_dict, headlines):
    """
    Format the signal + relevant headlines into a compact context string for Claude.
    """
    lines = []

    if domain == "crypto_move":
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

    elif domain == "oilgas_move":
        wti_price, wti_chg = signal_dict.get("wti_price"), signal_dict.get("wti_chg")
        ng_price, ng_chg = signal_dict.get("ng_price"), signal_dict.get("ng_chg")
        if wti_price is not None:
            lines.append(f"WTI crude: ${wti_price} ({wti_chg:+.1f}% vs prior reading)")
        if ng_price is not None:
            lines.append(f"Henry Hub natural gas: ${ng_price} ({ng_chg:+.1f}% vs prior reading)")
        lines.append("Source: FRED (DCOILWTICO, MHHNGSP)")

    elif domain == "brokerage_options":
        pcr = signal_dict.get("pcr") or {}
        lines.append(f"SPY options: {pcr.get('calls', 0):,} calls / {pcr.get('puts', 0):,} puts, put/call ratio {pcr.get('pcr')}")
        if signal_dict.get("vix") is not None:
            lines.append(f"VIX: {signal_dict['vix']:.1f}")

    elif domain == "betting_business":
        dknq_price, dknq_5d = signal_dict.get("dknq_price"), signal_dict.get("dknq_5d")
        flut_price, flut_5d = signal_dict.get("flut_price"), signal_dict.get("flut_5d")
        if dknq_price is not None:
            lines.append(f"DraftKings ($DKNG): ${dknq_price} ({dknq_5d:+.1f}% 5-day)")
        if flut_price is not None:
            lines.append(f"Flutter/FanDuel ($FLUT): ${flut_price} ({flut_5d:+.1f}% 5-day)")
        lines.append("This is sportsbook-operator stock performance — not betting odds, picks, or advice.")

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

def call_claude_cli(context, voice_addon=None):
    """
    Generate tweet text by piping a prompt into the local `claude` CLI.
    Uses the active Claude Code session — no API key or billing required.
    voice_addon is the domain-specific persona note from VOICE_ADDONS, appended
    to the shared base voice so each vertical's audience gets appropriately
    tailored content instead of one generic tone (see VOICE_ADDONS above).
    """
    import subprocess

    system_prompt = VOICE_SYSTEM_PROMPT_BASE + VOICE_ADDONS.get(voice_addon, "")
    prompt = f"{system_prompt}\n\nData:\n{context}"

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
        "crypto_move":        all_headlines.get("crypto", []),
        "crypto_sentiment":   all_headlines.get("crypto", []),
        "crypto_dominance":   all_headlines.get("crypto", []),
        "market_vix":         all_headlines.get("markets", []),
        "market_spy":         all_headlines.get("markets", []),
        "market_general":     all_headlines.get("markets", []),
        "oilgas_move":        all_headlines.get("oilgas", []),
        "brokerage_options":  all_headlines.get("brokerage", []),
        "betting_business":   all_headlines.get("betting", []),
        "baseball_allstar":   all_headlines.get("baseball", []),
        "baseball_games":     all_headlines.get("baseball", []),
    }
    headlines = headline_map.get(domain, [])

    context = build_context_string(domain, signal_dict, headlines)
    print(f"  Calling Claude... (context: {len(context)} chars)")

    draft = call_claude_cli(context, voice_addon=domain)

    # Hard cap — never exceed X's limit
    return draft[:270]
