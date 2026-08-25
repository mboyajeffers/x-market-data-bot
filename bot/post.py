#!/usr/bin/env python3
"""
X Post Bot — @Mboya_Jeffers
Generates a fresh data card and posts it to X with an auto-generated caption.

Usage:
    python3 post.py finance            # generate card + post live
    python3 post.py worldcup --dry-run # preview caption + card path, no API call
    python3 post.py crypto --dry-run
    python3 post.py betting

Supported verticals:
    finance, crypto, oilgas, brokerage, compliance, betting, gaming,
    ecommerce, media, solar, weather, worldcup

Required env vars (add to ~/.zshrc or ~/.x_bot_env):
    X_API_KEY
    X_API_SECRET
    X_ACCESS_TOKEN
    X_ACCESS_TOKEN_SECRET

Optional (Telegram alerts):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Install deps (once):
    pip install tweepy yfinance

Cron — Mac (local Eastern time, DST-aware):
    See crontab for full schedule. Key entries:
    0 13 * * *  worldcup (1PM ET daily — before afternoon/evening kickoffs)
    0 14 * * 1  betting (Monday afternoon)
    30 8 * * 1  finance (Monday morning)

Cron — GitHub Actions (Mac-independent, UTC): see .github/workflows/
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── PATHS ────────────────────────────────────────────────────────────────────

BOT_DIR     = Path(__file__).parent.resolve()
SCRIPTS_DIR = BOT_DIR.parent / "scripts"
CARDS_DIR   = BOT_DIR.parent / "cards"
LOG_PATH    = BOT_DIR / "post_log.json"
ERROR_LOG   = BOT_DIR / "error.log"
TODAY       = datetime.now().strftime("%Y-%m-%d")
NOW         = datetime.now().strftime("%Y-%m-%d %H:%M")

# ─── AFFILIATE CONFIG ─────────────────────────────────────────────────────────

sys.path.insert(0, str(BOT_DIR))
from affiliate_config import (  # noqa: E402
    VERTICAL_CASHTAGS, VERTICAL_CTA, THREAD_REPLIES, REQUIRES_DISCLOSURE, BIO_LINK
)
import verify  # noqa: E402

# ─── VERTICALS ────────────────────────────────────────────────────────────────

VERTICALS = {
    "finance":    "generate_finance_x_card.py",
    "crypto":     "generate_crypto_x_card.py",
    "oilgas":     "generate_oilgas_x_card.py",
    "brokerage":  "generate_brokerage_x_card.py",
    "compliance": "generate_compliance_x_card.py",
    "betting":    "generate_betting_x_card.py",
    "gaming":     "generate_gaming_x_card.py",
    "ecommerce":  "generate_ecommerce_x_card.py",
    "media":      "generate_media_x_card.py",
    "solar":      "generate_solar_x_card.py",
    "weather":    "generate_weather_x_card.py",
    "worldcup":   "generate_worldcup_x_card.py",
    "cannabis":   "generate_cannabis_x_card.py",
    "insight":    None,   # text-only — no card generator
    "signal":     "generate_signal_x_card.py",
}

CARD_NAMES = {
    "finance":    f"finance_x_card_{TODAY}.png",
    "crypto":     f"crypto_x_card_{TODAY}.png",
    "oilgas":     f"oilgas_x_card_{TODAY}.png",
    "brokerage":  f"brokerage_x_card_{TODAY}.png",
    "compliance": f"compliance_x_card_{TODAY}.png",
    "betting":    f"betting_x_card_{TODAY}.png",
    "gaming":     f"gaming_x_card_{TODAY}.png",
    "ecommerce":  f"ecommerce_x_card_{TODAY}.png",
    "media":      f"media_x_card_{TODAY}.png",
    "solar":      f"solar_x_card_{TODAY}.png",
    "weather":    f"weather_x_card_{TODAY}.png",
    "worldcup":   f"worldcup_x_card_{TODAY}.png",
    "cannabis":   f"cannabis_x_card_{TODAY}.png",
    "insight":    None,   # text-only — no card file
    "signal":     f"signal_x_card_{TODAY}.png",
}

# Verticals that post text only (no card, no media upload)
TEXT_ONLY_VERTICALS = {"insight"}

# ─── LOGGING ─────────────────────────────────────────────────────────────────

def log_post(vertical, tweet_id, card_path, caption):
    data = {"posts": []}
    if LOG_PATH.exists():
        try:
            data = json.loads(LOG_PATH.read_text())
        except Exception:
            pass
    data["posts"].append({
        "vertical":       vertical,
        "post_type":      "text" if card_path is None else "card",
        "date":           TODAY,
        "tweet_id":       str(tweet_id),
        "card_path":      str(card_path) if card_path is not None else None,
        "caption":        caption,
        "timestamp":      NOW,
        "thread_pending": THREAD_REPLIES.get(vertical) is not None,
        "thread_posted":  False,
    })
    LOG_PATH.write_text(json.dumps(data, indent=2))
    print(f"Logged: tweet {tweet_id} → {LOG_PATH}")


def log_error(vertical, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{ts}] [{vertical.upper()}] {msg}\n")
    print(f"ERROR [{vertical}]: {msg}", file=sys.stderr)

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def notify_telegram(msg):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        urllib.request.urlopen(urllib.request.Request(url, body), timeout=10)
    except Exception as e:
        print(f"Telegram alert failed: {e}")

# ─── MINIMAL DATA FETCHERS (caption only — fast, targeted) ───────────────────

def _yf_5d(ticker):
    """Single ticker 5-day return. Returns (latest_price, ret_5d) or (None, None)."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="10d")
        if hist.empty:
            return None, None
        closes = hist["Close"].dropna().tolist()
        ret5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else \
                (closes[-1] - closes[0]) / closes[0] * 100
        return round(closes[-1], 2), round(ret5d, 2)
    except Exception:
        return None, None


def _yf_since(ticker, start="2026-06-11"):
    """Return % change since a baseline date."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(start=start)
        if hist.empty or len(hist) < 2:
            return None, None
        closes = hist["Close"].dropna().tolist()
        ret = (closes[-1] - closes[0]) / closes[0] * 100
        return round(closes[-1], 2), round(ret, 2)
    except Exception:
        return None, None


def _coingecko(path, retries=3):
    url = f"https://api.coingecko.com/api/v3{path}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json", "User-Agent": "Mozilla/5.0"
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(20); continue
            return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(5); continue
            return None


def _fear_greed():
    try:
        req = urllib.request.Request(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())["data"][0]
            return int(d["value"]), d["value_classification"]
    except Exception:
        return None, None


def _edgar_count(query, form, days=30):
    from datetime import timedelta
    end = datetime.now()
    start = (end - timedelta(days=days)).strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q={urllib.parse.quote(query)}"
        f"&forms={form}&dateRange=custom&startdt={start}&enddt={end_s}"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "mboya-x-market-data-bot/1.0 (github.com/mboyajeffers/x-market-data-bot)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        return data.get("hits", {}).get("total", {}).get("value", 0)
    except Exception:
        return 0


def _fred_latest(series_id):
    """Return most recent non-null value from a FRED series (Federal Reserve)."""
    import csv
    import io
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mboya-x-market-data-bot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8")
        rows = []
        for row in csv.reader(io.StringIO(text)):
            if len(row) == 2 and row[0] not in ("DATE", "observation_date") and row[1].strip() not in (".", ""):
                try:
                    rows.append(float(row[1]))
                except ValueError:
                    pass
        return rows[-1] if rows else None
    except Exception:
        return None


def _okx_get(path):
    """Fetch from OKX public API — no auth required, no US geo-block."""
    url = f"https://www.okx.com{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _binance_funding_rate():
    """BTC-USD-SWAP 8hr funding rate via OKX. Returns (rate_pct, label) or (None, None).
    Verifiable at: okx.com/api/v5/public/funding-rate?instId=BTC-USD-SWAP
    """
    try:
        data = _okx_get("/api/v5/public/funding-rate?instId=BTC-USD-SWAP")
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
    except Exception:
        pass
    return None, None


def _binance_oi():
    """BTC open interest in USD via OKX BTC-USD-SWAP.
    Verifiable at: okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USD-SWAP
    """
    try:
        data = _okx_get("/api/v5/public/open-interest?instType=SWAP&instId=BTC-USD-SWAP")
        if data and data.get("code") == "0" and data.get("data"):
            return float(data["data"][0].get("oiUsd") or 0)
    except Exception:
        pass
    return None

# ─── CAPTION HELPERS ─────────────────────────────────────────────────────────

def _append_cta(parts, vertical):
    """Append cashtags, CTA, and FTC disclosure to a parts list."""
    cashtags = VERTICAL_CASHTAGS.get(vertical, "")
    cta      = VERTICAL_CTA[vertical]
    if cashtags:
        parts.append(f"\n{cashtags}")
    parts.append(f"\n{cta}")
    if vertical in REQUIRES_DISCLOSURE:
        parts.append("#ad")


_ATTRIBUTION_PREFIXES = ("source:", "not investment", "not legal", "not tax", "not betting")


def _finalize_caption(parts, vertical):
    """Join a caption's data-only parts and append the CTA/disclosure, trimming
    the DATA portion (not the CTA) if the combined length would exceed X's
    280-char limit. The plain `_append_cta` + `[:280]` pattern used elsewhere
    truncates blindly from the end, which risks silently cutting a referral
    URL in half — this guarantees the CTA/#ad always survives intact instead.

    Every caller's trailing 1-2 parts are a source/disclaimer line (checked
    against the same phrases verify.py's has_source check looks for) — those
    get protected the same way the CTA does. An earlier version only
    protected the CTA and trimmed disclaimer lines like any other body
    content; found 2026-08-24 that this dropped finance/brokerage's whole
    source line over as little as a 3-char overage even though the final
    caption had 5-9 chars of unused budget to spare."""
    cashtags = VERTICAL_CASHTAGS.get(vertical, "")
    cta      = VERTICAL_CTA[vertical]
    suffix_parts = []
    if cashtags:
        suffix_parts.append(f"\n{cashtags}")
    suffix_parts.append(f"\n{cta}")
    if vertical in REQUIRES_DISCLOSURE:
        suffix_parts.append("#ad")

    # Peel trailing attribution/disclaimer parts off into the protected suffix.
    parts = list(parts)
    attribution = []
    while parts and parts[-1].strip().lower().startswith(_ATTRIBUTION_PREFIXES):
        attribution.insert(0, parts.pop())
    if attribution:
        suffix_parts = [f"\n{a}" for a in attribution] + suffix_parts

    suffix = "\n".join(suffix_parts)
    body   = "\n".join(parts)
    budget = 280 - len(suffix)
    if budget < 0:
        # CTA itself exceeds 280 chars — shouldn't happen; never truncate it silently.
        return suffix[:280]
    if len(body) <= budget:
        return body + suffix
    # Trim to the last complete word that fits, not a raw character cut —
    # a hard [:budget] slice can land mid-word (e.g. "Source: EIA..." -> "Sourc").
    # Word-level, not line-level: an earlier line-level version dropped an
    # entire 54-char source-attribution line over a 3-char overage (found
    # 2026-08-24 on finance/brokerage) — wasteful when there's clearly room.
    import re
    tokens = re.split(r"(\s+)", body)  # keeps whitespace/newlines as their own tokens
    trimmed, used = [], 0
    for tok in tokens:
        if used + len(tok) > budget:
            break
        trimmed.append(tok)
        used += len(tok)
    return "".join(trimmed).rstrip() + suffix

# ─── CAPTION BUILDERS ────────────────────────────────────────────────────────

def build_caption_finance():
    sector_map = [
        ("XLE","Energy"), ("XLK","Tech"), ("XLI","Industrials"),
        ("XLF","Financials"), ("XLV","Health"), ("XLP","Staples"),
    ]
    results = []
    for sym, name in sector_map:
        _, ret = _yf_5d(sym)
        if ret is not None:
            results.append((name, ret))
        time.sleep(0.15)
    spy_price, spy_ret = _yf_5d("SPY")
    vix, _    = _yf_5d("^VIX")
    ten_y     = _fred_latest("DGS10")
    fed       = _fred_latest("FEDFUNDS")
    t10y2y    = _fred_latest("T10Y2Y")
    ig_spread = _fred_latest("BAMLC0A0CM")

    if results:
        top = max(results, key=lambda x: x[1])
        bot = min(results, key=lambda x: x[1])
        parts = [f"Finance Weekly — {TODAY}\n"]
        parts.append(f"Best:  {top[0]}  {top[1]:+.1f}%")
        parts.append(f"Worst: {bot[0]}  {bot[1]:+.1f}%")
        spy_line = f"SPY 5d: {spy_ret:+.1f}%" if spy_ret is not None else ""
        if vix is not None:
            spy_line += f"  |  VIX: {vix:.1f}"
        if spy_line:
            parts.append(spy_line)
        macro_parts = []
        if ten_y is not None:
            macro_parts.append(f"10Y: {ten_y:.2f}%")
        if fed is not None:
            macro_parts.append(f"Fed: {fed:.2f}%")
        if macro_parts:
            parts.append("  |  ".join(macro_parts))
        # Practitioner layer: yield curve + IG credit spread
        if t10y2y is not None:
            curve_label = "INVERTED" if t10y2y < 0 else "normal"
            ctx = f"Curve: {t10y2y:+.2f}% ({curve_label})"
            if ig_spread is not None:
                ctx += f"  |  IG: {ig_spread:.0f}bps"
            parts.append(ctx)
        parts.append("\nSource: Yahoo Finance · FRED  |  Not investment advice.")
        return _finalize_caption(parts, "finance")

    parts = [f"Finance Weekly — {TODAY}. Live S&P 500 sector data."]
    parts.append("Source: Yahoo Finance · FRED  |  Not investment advice.")
    return _finalize_caption(parts, "finance")


def build_caption_crypto():
    fg_val, fg_label = _fear_greed()
    markets = _coingecko(
        "/coins/markets?vs_currency=usd&order=market_cap_desc"
        "&per_page=20&page=1&sparkline=false&price_change_percentage=7d,24h"
    )
    btc_30d  = _coingecko("/coins/bitcoin/market_chart?vs_currency=usd&days=30&interval=daily")
    eth_30d  = _coingecko("/coins/ethereum/market_chart?vs_currency=usd&days=30&interval=daily")
    global_d = _coingecko("/global")
    fr, fr_label = _binance_funding_rate()

    # Pull 24h data for BTC and ETH directly from markets
    btc_24h = eth_24h = None
    if markets:
        btc_row = next((m for m in markets if m["symbol"] == "btc"), None)
        eth_row = next((m for m in markets if m["symbol"] == "eth"), None)
        if btc_row:
            btc_24h = btc_row.get("price_change_percentage_24h_in_currency")
        if eth_row:
            eth_24h = eth_row.get("price_change_percentage_24h_in_currency")

    # Determine if there's a notable 24h move (> ±3%) worth leading with
    notable_24h = (btc_24h is not None and abs(btc_24h) >= 3.0) or \
                  (eth_24h is not None and abs(eth_24h) >= 3.0)

    parts = [f"Crypto — {TODAY}\n"]

    if fg_val is not None:
        parts.append(f"Fear & Greed: {fg_val} ({fg_label})")

    # Lead with 24h if notable, otherwise 7d
    if notable_24h:
        btc_str = f"BTC 24h: {btc_24h:+.1f}%" if btc_24h is not None else ""
        eth_str = f"ETH 24h: {eth_24h:+.1f}%" if eth_24h is not None else ""
        parts.append("  |  ".join(x for x in [btc_str, eth_str] if x))
    else:
        if markets:
            by_7d = sorted(
                [m for m in markets if m.get("price_change_percentage_7d_in_currency")],
                key=lambda m: m["price_change_percentage_7d_in_currency"],
                reverse=True
            )
            if by_7d:
                t = by_7d[0]
                parts.append(f"Top 7d: {t['symbol'].upper()} {t['price_change_percentage_7d_in_currency']:+.1f}%")

    if btc_30d:
        px = [p[1] for p in btc_30d["prices"]]
        if len(px) >= 2:
            parts.append(f"BTC 30d: {(px[-1]/px[0]-1)*100:+.1f}%")

    if eth_30d:
        px = [p[1] for p in eth_30d["prices"]]
        if len(px) >= 2:
            parts.append(f"ETH 30d: {(px[-1]/px[0]-1)*100:+.1f}%")

    if global_d:
        btc_dom = global_d["data"]["market_cap_percentage"].get("btc", 0)
        total   = global_d["data"]["total_market_cap"]["usd"] / 1e12
        parts.append(f"BTC dom: {btc_dom:.1f}%  |  Mkt cap: ${total:.2f}T")

    # Practitioner layer: BTC funding rate (cascade risk signal)
    if fr is not None:
        parts.append(f"BTC funding: {fr:+.4f}% ({fr_label})")

    parts.append("\nSource: CoinGecko · alternative.me · OKX")
    parts.append("Not investment advice.")
    return _finalize_caption(parts, "crypto")


def build_caption_oilgas():
    cl_price, cl_ret = _yf_5d("CL=F")
    ng_price, ng_ret = _yf_5d("NG=F")
    xle, xle_ret     = _yf_5d("XLE")
    slb, slb_ret     = _yf_5d("SLB")
    cushing          = _fred_latest("WCESTUS1")
    ref_util         = _fred_latest("WPULEUS3")

    parts = [f"Energy Weekly — {TODAY}\n"]
    if cl_price is not None:
        parts.append(f"WTI Crude: ${cl_price:.2f}  ({cl_ret:+.1f}% 5d)")
    if ng_price is not None:
        parts.append(f"Henry Hub: ${ng_price:.3f}/MMBtu  ({ng_ret:+.1f}% 5d)")
    if xle_ret is not None:
        parts.append(f"XLE ETF: {xle_ret:+.1f}% 5d")
    if cl_price and ng_price:
        ratio = cl_price / (ng_price * 6)
        parts.append(f"Oil/Gas BTU ratio: {ratio:.1f}x")
    # Practitioner layer: Cushing stocks + refinery utilization
    if cushing is not None:
        ctx = f"Cushing: {cushing:.1f}M bbls"
        if ref_util is not None:
            ctx += f"  |  Refinery util: {ref_util:.1f}%"
        parts.append(ctx)
    parts.append("\nSource: EIA via FRED · Yahoo Finance (NYMEX)  |  Not investment advice.")
    return _finalize_caption(parts, "oilgas")


def build_caption_brokerage():
    spy_price, spy_ret = _yf_5d("SPY")
    vix, _             = _yf_5d("^VIX")
    gs,   gs_ret       = _yf_5d("GS")
    ms,   ms_ret       = _yf_5d("MS")
    schw, schw_ret     = _yf_5d("SCHW")
    ten_y              = _fred_latest("DGS10")
    t10y2y             = _fred_latest("T10Y2Y")
    hy_spread          = _fred_latest("BAMLH0A0HYM2")

    parts = [f"Brokerage Weekly — {TODAY}\n"]
    if spy_ret is not None:
        parts.append(f"SPY: ${spy_price:.2f}  ({spy_ret:+.1f}% 5d)")
    if vix is not None:
        regime = "High Vol" if vix > 25 else ("Elevated" if vix > 18 else "Low Vol")
        parts.append(f"VIX: {vix:.1f}  ({regime})")
    if ten_y is not None:
        parts.append(f"10Y Yield: {ten_y:.2f}%")
    broker_line = "  |  ".join(
        f"{sym}: {ret:+.1f}%"
        for sym, ret in [("GS", gs_ret), ("MS", ms_ret), ("SCHW", schw_ret)]
        if ret is not None
    )
    if broker_line:
        parts.append(broker_line)
    # Practitioner layer: yield curve + HY credit spread
    if t10y2y is not None:
        curve_label = "INVERTED" if t10y2y < 0 else "normal"
        ctx = f"Curve: {t10y2y:+.2f}% ({curve_label})"
        if hy_spread is not None:
            ctx += f"  |  HY: {hy_spread:.0f}bps"
        parts.append(ctx)
    parts.append("\nSource: Yahoo Finance · FRED  |  Not investment advice.")
    return _finalize_caption(parts, "brokerage")


def build_caption_compliance():
    ap   = _edgar_count("", "AP",  days=30)
    aae  = _edgar_count("", "AAE", days=30)
    inv  = _edgar_count('"SEC investigation"', "8-K", days=30)
    s1   = _edgar_count("", "S-1", days=30)

    level = "ELEVATED" if (ap + aae) > 10 else ("MODERATE" if (ap + aae) > 4 else "NORMAL")
    parts = [f"SEC Activity — {TODAY}\n"]
    parts.append(f"Admin. Proceedings (30d):  {ap}")
    parts.append(f"Acctg Enforcement (30d):   {aae}")
    parts.append(f"Investigation 8-Ks (30d):  {inv}")
    parts.append(f"S-1 Registrations (30d):   {s1}")
    parts.append(f"\nEnforcement level: {level}")
    parts.append("\nSource: SEC EDGAR (public filings)")
    return _finalize_caption(parts, "compliance")


def build_caption_betting():
    _, dkng = _yf_5d("DKNG"); _, penn = _yf_5d("PENN")
    _, flut = _yf_5d("FLUT"); _, betz = _yf_5d("BETZ")
    _, spy  = _yf_5d("SPY")

    m = datetime.now().month
    is_worldcup = m in (6, 7)

    parts = []

    if is_worldcup:
        # Lead with FIFA live match data during World Cup
        today     = _fetch_wc_today()
        yesterday = _fetch_wc_yesterday()

        finished = [x for x in today if x["state"] == "post"]
        live_now = [x for x in today if x["state"] == "in"]
        upcoming = [x for x in today if x["state"] == "pre"]

        parts.append(f"WC2026 Betting — {TODAY}\n")

        if finished:
            lines = [f"{x['home']} {x['h_score']}-{x['a_score']} {x['away']}"
                     for x in finished[:3]]
            parts.append("FT: " + "  ·  ".join(lines))
        if live_now:
            lines = [f"{x['home']} {x['h_score']}-{x['a_score']} {x['away']}"
                     for x in live_now[:2]]
            parts.append("LIVE: " + "  ·  ".join(lines))
        if upcoming:
            pairs = [f"{x['home']}-{x['away']}" for x in upcoming[:3]]
            t = upcoming[0]["time"]
            t = "" if t.lower() in ("scheduled", "") else f"  {t}"
            parts.append("Today: " + " · ".join(pairs) + t)
        elif not finished and not live_now:
            yest_finished = [x for x in yesterday if x["state"] == "post"]
            if yest_finished:
                lines = [f"{x['home']} {x['h_score']}-{x['a_score']} {x['away']}"
                         for x in yest_finished[:3]]
                parts.append("Yest: " + "  ·  ".join(lines))

        usa_line = _usa_result_line(today) or _usa_result_line(yesterday)
        if usa_line:
            parts.append(f"\n🇺🇸 {usa_line}")

        tickers = [("DKNG", dkng), ("FLUT", flut), ("BETZ", betz)]
        stock_line = "  ".join(f"{s}: {r:+.1f}%" for s, r in tickers if r is not None)
        if stock_line:
            parts.append(f"\n{stock_line}")

        parts.append("\nNot investment advice.")
    else:
        season = ("NFL Playoffs · NBA · NHL"  if m in (1, 2) else
                  "NFL Season · MLB · NBA"    if m in (9, 10) else
                  "NFL · NBA · NHL · MLB")
        parts.append(f"Betting Sector — {TODAY}\n")
        tickers = [("DKNG", dkng), ("PENN", penn), ("FLUT", flut), ("BETZ ETF", betz)]
        for sym, ret in tickers:
            if ret is not None:
                parts.append(f"{sym}: {ret:+.1f}%")
        if spy is not None:
            parts.append(f"SPY: {spy:+.1f}%")
        parts.append(f"\nActive: {season}")
        parts.append("\nSource: Yahoo Finance  |  Not investment advice.")

    return _finalize_caption(parts, "betting")


def build_caption_gaming():
    _, rblx = _yf_5d("RBLX"); _, ttwo = _yf_5d("TTWO")
    _, ea   = _yf_5d("EA");   _, espo = _yf_5d("ESPO")
    _, spy  = _yf_5d("SPY")
    parts = [f"Gaming Sector — {TODAY}\n"]
    tickers = [("RBLX", rblx), ("TTWO", ttwo), ("EA", ea), ("ESPO ETF", espo)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    parts.append("\nSource: Yahoo Finance")
    parts.append("Not investment advice.")
    return _finalize_caption(parts, "gaming")


def build_caption_ecommerce():
    _, amzn  = _yf_5d("AMZN"); _, shop = _yf_5d("SHOP")
    _, etsy  = _yf_5d("ETSY"); _, spy  = _yf_5d("SPY")
    delinq   = _fred_latest("DRCCLACBN")
    parts = [f"E-Commerce Sector — {TODAY}\n"]
    tickers = [("AMZN", amzn), ("SHOP", shop), ("ETSY", etsy)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    # Practitioner layer: CC delinquency (consumer stress leading indicator)
    if delinq is not None:
        stress = " elevated ⚠" if delinq > 3.0 else " (normal range)"
        parts.append(f"\nCC delinquency: {delinq:.1f}%{stress}")
    parts.append("\nSource: Yahoo Finance · FRED  |  Not investment advice.")
    return _finalize_caption(parts, "ecommerce")


def build_caption_media():
    _, nflx = _yf_5d("NFLX"); _, dis  = _yf_5d("DIS")
    _, spot = _yf_5d("SPOT"); _, roku = _yf_5d("ROKU")
    _, spy  = _yf_5d("SPY")
    parts = [f"Media & Streaming — {TODAY}\n"]
    tickers = [("NFLX", nflx), ("DIS", dis), ("SPOT", spot), ("ROKU", roku)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    parts.append("\nSource: Yahoo Finance")
    parts.append("Not investment advice.")
    return _finalize_caption(parts, "media")


def build_caption_solar():
    _, fslr    = _yf_5d("FSLR"); _, enph = _yf_5d("ENPH")
    _, tan     = _yf_5d("TAN");  _, spy  = _yf_5d("SPY")
    ng_price, ng_ret = _yf_5d("NG=F")
    parts = [f"Clean Energy Sector — {TODAY}\n"]
    tickers = [("FSLR", fslr), ("ENPH", enph), ("TAN ETF", tan)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    # Practitioner layer: Henry Hub NG (solar competes with gas peakers, not oil)
    if ng_price is not None:
        parts.append(f"\nHenry Hub: ${ng_price:.2f}/MMBtu ({ng_ret:+.1f}% 5d) — solar breakeven ~$3.50")
    else:
        parts.append("\nHenry Hub NG context in card (solar vs gas peaker economics).")
    parts.append("\nSource: Yahoo Finance · FRED  |  Not investment advice.")
    return _finalize_caption(parts, "solar")


def build_caption_weather():
    import json as _json
    cities = [
        ("New York", 40.71, -74.01, "America/New_York"),
        ("Miami",    25.77, -80.19, "America/New_York"),
        ("Chicago",  41.85, -87.65, "America/Chicago"),
    ]
    conditions = []
    for name, lat, lon, tz in cities:
        url = (f"https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               f"&current=temperature_2m,weather_code"
               f"&temperature_unit=fahrenheit&timezone={tz}&forecast_days=1")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mboya-x-market-data-bot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = _json.loads(r.read())
            conditions.append((name, d["current"]["temperature_2m"]))
        except Exception:
            pass
        time.sleep(0.3)
    parts = [f"US Weather Snapshot — {TODAY}\n"]
    for city, temp in conditions:
        parts.append(f"{city}: {temp:.0f}\u00b0F")
    parts.append("\n8 cities · 7-day forecast in card.")
    parts.append("\nSource: Open-Meteo (WMO-compliant, open-meteo.com)")
    return _finalize_caption(parts, "weather")


def _fetch_wc_scoreboard(date_str):
    """Fetch World Cup scoreboard for a given YYYYMMDD date string."""
    url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
           f"fifa.world/scoreboard?dates={date_str}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        matches = []
        for event in data.get("events", []):
            comps       = event.get("competitions", [{}])[0]
            competitors = comps.get("competitors", [])
            if len(competitors) < 2:
                continue
            home    = competitors[0].get("team", {}).get("abbreviation", "")[:3]
            away    = competitors[1].get("team", {}).get("abbreviation", "")[:3]
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
            matches.append({"home": home, "away": away, "state": state,
                            "h_score": h_score, "a_score": a_score,
                            "time": time_str, "detail": detail, "is_usa": is_usa})
        return matches
    except Exception:
        return []


def _fetch_wc_today():
    return _fetch_wc_scoreboard(datetime.now().strftime("%Y%m%d"))


def _fetch_wc_yesterday():
    return _fetch_wc_scoreboard((datetime.now() - timedelta(days=1)).strftime("%Y%m%d"))


def _usa_result_line(matches):
    """Return a one-line USA result string from a match list, or ''."""
    m = next((x for x in matches if x["is_usa"]), None)
    if not m:
        return ""
    h, a, hs, as_ = m["home"], m["away"], m["h_score"], m["a_score"]
    try:
        h_g, a_g = int(hs or 0), int(as_ or 0)
        usa_home = h in ("USA", "US")
        usa_g    = h_g if usa_home else a_g
        opp_g    = a_g if usa_home else h_g
        opp      = a if usa_home else h
        outcome  = "W" if usa_g > opp_g else ("D" if usa_g == opp_g else "L")
        return f"USA {outcome} {usa_g}-{opp_g} {opp}"
    except Exception:
        return f"{h} {hs}-{as_} {a}"


def build_caption_worldcup():
    """
    Scores-first caption for the World Cup daily post.
    Structure: scores → USA angle → market signal → CTA + hashtags.
    No affiliate link in main tweet → no #ad required here (goes in thread reply).
    """
    _, dkng_ret = _yf_since("DKNG", "2026-06-11")
    _, spy_ret  = _yf_since("SPY",  "2026-06-11")

    d = datetime.now().month * 100 + datetime.now().day
    stage = ("Group Stage"   if d <= 627 else
             "Round of 32"   if d <= 704 else
             "Round of 16"   if d <= 709 else
             "Quarterfinals" if d <= 713 else
             "Semifinals"    if d <= 716 else
             "Final"         if d <= 719 else
             "Post-Tournament")

    today     = _fetch_wc_today()
    yesterday = _fetch_wc_yesterday()

    finished  = [m for m in today if m["state"] == "post"]
    live_now  = [m for m in today if m["state"] == "in"]
    upcoming  = [m for m in today if m["state"] == "pre"]

    parts = [f"World Cup 2026 | {stage}\n"]

    # ── SCORES ────────────────────────────────────────────────────
    if finished:
        lines = [f"{m['home']} {m['h_score']}-{m['a_score']} {m['away']}"
                 for m in finished[:4]]
        parts.append("FT: " + "  ·  ".join(lines))

    if live_now:
        lines = [f"{m['home']} {m['h_score']}-{m['a_score']} {m['away']}"
                 for m in live_now[:2]]
        parts.append("🔴 LIVE: " + "  ·  ".join(lines))

    if upcoming:
        # "Later: EGY-IRN · NZL-BEL  11PM ET" format — compact
        pairs = [f"{m['home']}-{m['away']}" for m in upcoming[:3]]
        t = upcoming[0]["time"]
        # Clean up fallback "Scheduled" text
        t = "" if t.lower() in ("scheduled", "") else f"  {t}"
        parts.append("Later: " + " · ".join(pairs) + t)

    # ── USA ANGLE ─────────────────────────────────────────────────
    usa_today = _usa_result_line(today)
    usa_yest  = _usa_result_line(yesterday)
    usa_line  = usa_today or (f"{usa_yest} yesterday" if usa_yest else "")
    if usa_line:
        parts.append(f"\n🇺🇸 {usa_line}")

    # ── MARKET SIGNAL (one line, secondary) ──────────────────────
    mk_parts = []
    if dkng_ret is not None: mk_parts.append(f"$DKNG {dkng_ret:+.1f}%")
    if spy_ret  is not None: mk_parts.append(f"SPY {spy_ret:+.1f}%")
    if mk_parts:
        parts.append("\n" + " · ".join(mk_parts) + " since Jun 11 kickoff · Not betting advice")

    # ── CTA + HASHTAGS ────────────────────────────────────────────
    # Bio link is a monetized destination → #ad included (conservative FTC posture).
    # #ad is protected the same way _finalize_caption protects it elsewhere —
    # this vertical is in REQUIRES_DISCLOSURE, so a blind [:280] cut that
    # lands on the suffix (as the old version of this function did) risks
    # silently shipping a post with no FTC disclosure.
    from affiliate_config import VERTICAL_CTA
    wc_cta = VERTICAL_CTA.get("worldcup", BIO_LINK)
    usa_tag = " #USMNT" if (usa_today or usa_yest) else ""
    suffix = f"\n{wc_cta}\n#WorldCup2026{usa_tag} #ad"
    body   = "\n".join(parts)
    budget = 280 - len(suffix)
    if len(body) > budget:
        import re
        tokens, trimmed, used = re.split(r"(\s+)", body), [], 0
        for tok in tokens:
            if used + len(tok) > budget:
                break
            trimmed.append(tok)
            used += len(tok)
        body = "".join(trimmed).rstrip()
    return body + suffix


def build_caption_cannabis():
    _, mj    = _yf_5d("MJ")
    _, curlf = _yf_5d("CURLF")
    _, gtbif = _yf_5d("GTBIF")
    parts = [f"NYC Cannabis — {TODAY}"]
    parts.append("280E: $1M store → ~$52K/yr extra fed tax")
    parts.append("NY excise: tier calc — most POS systems wrong")
    parts.append("OCM audits active · Metrc is #1 trigger")
    # $MJ omitted here — it's already added as the vertical's cashtag suffix below.
    mso = [f"{s}: {r:+.1f}%" for s, r in [("MJ", mj), ("CURLF", curlf), ("GTBIF", gtbif)]
           if r is not None]
    if mso:
        parts.append("MSO 5d: " + "  ".join(mso))
    parts.append("\nSource: IRC 280E · NY DTF")
    return _finalize_caption(parts, "cannabis")


def build_caption_insight():
    from insight import build_caption_insight as _build
    return _build()


def build_caption_signal():
    """Read last_signal.json and build outcome card caption."""
    import json as _json
    from affiliate_config import GUMROAD_SIGNAL_URL, SIGNAL_PRICE
    local_path = CARDS_DIR.parent / "data" / "last_signal.json"
    if not local_path.exists():
        return (
            "Morning Signals — no data yet.\n\n"
            f"Launching shortly: pre-market equity signals {SIGNAL_PRICE}\n"
            f"{GUMROAD_SIGNAL_URL}\n\n"
            "#QuantTrading #SwingTrading"
        )
    data    = _json.loads(local_path.read_text())
    signals = data.get('signals', [])
    regime  = data.get('regime', 'CLEAR')
    if not signals:
        return (
            f"No signals cleared the confidence bar today.\n\n"
            f"Regime: {regime}. The model only flags setups it believes in.\n\n"
            f"Subscribers get pre-market alerts when it does fire.\n"
            f"{GUMROAD_SIGNAL_URL}\n\n"
            "#QuantTrading #Signals"
        )
    lines = []
    for s in signals:
        arrow = '▲' if s['direction'] == 'LONG' else '▼'
        lines.append(f"{s['symbol']} {arrow} [{s['confidence']:.0%}]")
    signal_list = " · ".join(lines)
    footer = (
        f"\n\nFlagged pre-market 6:15am. Not investment advice.\n"
        f"Full reasoning → {GUMROAD_SIGNAL_URL}\n"
        "#QuantTrading #Signals"
    )
    # Defense-in-depth: a busier signal day (more tickers) could still push
    # this over 280 — trim to a count-only summary rather than ship an
    # over-length caption that verify.py would just FAIL anyway.
    body = f"Today's signals: {signal_list}"
    if len(body) + len(footer) > 280:
        body = f"{len(signals)} signals fired today (full list for subscribers)"
    return body + footer


CAPTION_BUILDERS = {
    "finance":    build_caption_finance,
    "crypto":     build_caption_crypto,
    "oilgas":     build_caption_oilgas,
    "brokerage":  build_caption_brokerage,
    "compliance": build_caption_compliance,
    "betting":    build_caption_betting,
    "gaming":     build_caption_gaming,
    "ecommerce":  build_caption_ecommerce,
    "media":      build_caption_media,
    "solar":      build_caption_solar,
    "weather":    build_caption_weather,
    "worldcup":   build_caption_worldcup,
    "cannabis":   build_caption_cannabis,
    "insight":    build_caption_insight,
    "signal":     build_caption_signal,
}

# ─── TWEEPY AUTH ─────────────────────────────────────────────────────────────

def get_clients():
    """Returns (tweepy.Client v2, tweepy.API v1.1). Exits on missing env vars."""
    try:
        import tweepy
    except ImportError:
        print("ERROR: tweepy not installed. Run: pip install tweepy")
        sys.exit(1)

    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing  = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        print("Add them to ~/.zshrc:  export X_API_KEY=...")
        sys.exit(1)

    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    auth   = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    api_v1 = tweepy.API(auth)

    return client, api_v1

# ─── POST ─────────────────────────────────────────────────────────────────────

def run_generator(vertical):
    """Runs the card generator script. Returns card path or exits on failure."""
    script = SCRIPTS_DIR / VERTICALS[vertical]
    card   = CARDS_DIR / CARD_NAMES[vertical]

    print(f"Generating {vertical} card...")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Generator failed (exit {result.returncode}): {err[-300:]}")

    if not card.exists():
        raise RuntimeError(f"Generator finished but card not found: {card}")

    # Print any ADJUSTED lines from the overlap auto-fixer
    for line in result.stdout.splitlines():
        if line.startswith("ADJUSTED") or line.startswith("WARNING") or line.startswith("Overlap"):
            print(f"[card_validator] {line}")

    # Optional Claude vision QA — enable with: export CLAUDE_VISION_QA=1
    if os.getenv("CLAUDE_VISION_QA") == "1":
        import sys as _sys
        _sys.path.insert(0, str(SCRIPTS_DIR))
        from card_validator import claude_vision_qa
        ok, notes = claude_vision_qa(str(card))
        if not ok:
            print(f"[VISION QA WARNING] {notes}")

    print(f"Card ready: {card}")
    return card


def publish(vertical, card_path, caption, dry_run=False):
    """Post a pre-built card + caption to X.

    Shared by post_to_x (fresh generation) and the xbot CLI (frozen staging
    content). Handles auth, media upload, tweet creation, logging, and the
    Telegram notification. Returns the tweet_id, or None on dry_run.
    """
    print(f"\n--- CAPTION ({len(caption)} chars) ---\n{caption}\n---\n")

    if dry_run:
        print(f"DRY RUN — card: {card_path}")
        thread_text = THREAD_REPLIES.get(vertical)
        if thread_text:
            print(f"\n--- THREAD REPLY (90 min later) ---\n{thread_text}\n---\n")
        else:
            print("No thread reply configured for this vertical.")
        print("No post made. Remove --dry-run to post live.")
        return None

    # 1. Auth
    client, api_v1 = get_clients()

    # 2. Upload media (v1.1) — skipped for text-only posts
    if card_path is not None:
        print("Uploading image...")
        media = api_v1.media_upload(filename=str(card_path))
        print(f"Media ID: {media.media_id}")
        media_ids = [media.media_id]
    else:
        media_ids = None

    # 3. Post tweet (v2)
    print("Posting tweet...")
    if media_ids:
        response = client.create_tweet(text=caption, media_ids=media_ids, user_auth=True)
    else:
        response = client.create_tweet(text=caption, user_auth=True)
    tweet_id = response.data["id"]
    print(f"Posted: https://x.com/Mboya_Jeffers/status/{tweet_id}")

    # 4. Log + notify
    log_post(vertical, tweet_id, card_path, caption)
    notify_telegram(
        f"Posted [{vertical}] — {TODAY}\n"
        f"https://x.com/Mboya_Jeffers/status/{tweet_id}"
    )

    return tweet_id


def post_to_x(vertical, dry_run=False):
    # 1. Generate card
    is_text_only = vertical in TEXT_ONLY_VERTICALS
    card_path = None if is_text_only else run_generator(vertical)

    # 2. Build caption
    print(f"Building caption for {vertical}...")
    caption = CAPTION_BUILDERS[vertical]()

    # 3. Verify before publishing. This is the same verify_all() the xbot CLI
    #    already runs via preview.py — automated callers (GitHub Actions) used
    #    to skip it entirely and publish unverified content. FAIL blocks the
    #    post (bad caption/data/card); PASS/WARN proceeds exactly as before.
    post_type = "text" if is_text_only else "card"
    verification = verify.verify_all(vertical, caption, card_path, post_type=post_type)
    print(verify.format_report(vertical, verification))
    if verification["status"] == verify.FAIL and not dry_run:
        reasons = "; ".join(
            f"{c['name']}: {c['detail']}"
            for c in verification["checks"] if c["status"] == verify.FAIL
        )
        log_error(vertical, f"Verification FAILED, post skipped — {reasons}")
        notify_telegram(f"SKIPPED [{vertical}] — verification FAILED: {reasons}")
        return None

    # 4. Publish (auth + upload + tweet + log + notify)
    return publish(vertical, card_path, caption, dry_run=dry_run)

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="X Post Bot — @Mboya_Jeffers")
    parser.add_argument("vertical", choices=list(VERTICALS.keys()),
                        help="Content vertical to post")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate card + preview caption, do not post")
    args = parser.parse_args()

    try:
        post_to_x(args.vertical, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
    except Exception as e:
        log_error(args.vertical, str(e))
        notify_telegram(f"Post FAILED [{args.vertical}] — {NOW}\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
