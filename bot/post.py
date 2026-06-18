#!/usr/bin/env python3
"""
X Post Bot — @Mboya_Jeffers
Generates a fresh data card and posts it to X with an auto-generated caption.

Usage:
    python3 post.py finance            # generate card + post live
    python3 post.py crypto --dry-run   # preview caption + card path, no API call
    python3 post.py oilgas
    python3 post.py brokerage
    python3 post.py compliance

Required env vars (add to ~/.zshrc):
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
    0 9 * * 1   /usr/bin/python3 ~/Claude_Projects/REVENUE/X/bot/post.py finance  >> /tmp/x_post_mon.log 2>&1
    0 9 * * 4   /usr/bin/python3 ~/Claude_Projects/REVENUE/X/bot/post.py crypto   >> /tmp/x_post_thu.log 2>&1

Cron — VM (UTC, adjust for DST manually):
    0 13 * * 1  cd /opt/cleanmetrics && source venv/bin/activate && python /opt/x_bot/post.py finance  >> /tmp/x_post.log 2>&1
    0 13 * * 4  cd /opt/cleanmetrics && source venv/bin/activate && python /opt/x_bot/post.py crypto   >> /tmp/x_post.log 2>&1
    # Change 13 → 14 in winter (EST = UTC-5)
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
from datetime import datetime
from pathlib import Path

# ─── PATHS ────────────────────────────────────────────────────────────────────

BOT_DIR     = Path(__file__).parent.resolve()
SCRIPTS_DIR = BOT_DIR.parent / "scripts"
CARDS_DIR   = BOT_DIR.parent / "cards"
LOG_PATH    = BOT_DIR / "post_log.json"
ERROR_LOG   = BOT_DIR / "error.log"
TODAY       = datetime.now().strftime("%Y-%m-%d")
NOW         = datetime.now().strftime("%Y-%m-%d %H:%M")

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
}

# ─── LOGGING ─────────────────────────────────────────────────────────────────

def log_post(vertical, tweet_id, card_path, caption):
    data = {"posts": []}
    if LOG_PATH.exists():
        try:
            data = json.loads(LOG_PATH.read_text())
        except Exception:
            pass
    data["posts"].append({
        "vertical":  vertical,
        "date":      TODAY,
        "tweet_id":  str(tweet_id),
        "card_path": str(card_path),
        "caption":   caption,
        "timestamp": NOW,
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
            "User-Agent": "CleanMetrics data-pipeline contact@cleanmetrics.io",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        return data.get("hits", {}).get("total", {}).get("value", 0)
    except Exception:
        return 0


def _fred_latest(series_id):
    """Return most recent non-null value from a FRED series (Federal Reserve)."""
    import csv, io
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CleanMetrics/1.0"})
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
    vix, _  = _yf_5d("^VIX")
    ten_y   = _fred_latest("DGS10")    # 10Y Treasury — Federal Reserve
    fed     = _fred_latest("FEDFUNDS") # Fed Funds Rate — Federal Reserve

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
        macro = ""
        if ten_y is not None:
            macro += f"10Y: {ten_y:.2f}%"
        if fed is not None:
            macro += f"  |  Fed: {fed:.2f}%"
        if macro:
            parts.append(macro)
        parts.append("\nSource: Yahoo Finance · FRED (Federal Reserve)")
        parts.append("Not investment advice.")
        parts.append("\n#Finance #Markets #DataEngineering")
        return "\n".join(parts)[:280]

    return (f"Finance Weekly — {TODAY}. Live S&P 500 sector data.\n"
            f"Source: Yahoo Finance · FRED\nNot investment advice.\n\n"
            f"#Finance #Markets #DataEngineering")[:280]


def build_caption_crypto():
    fg_val, fg_label = _fear_greed()
    markets = _coingecko(
        "/coins/markets?vs_currency=usd&order=market_cap_desc"
        "&per_page=20&page=1&sparkline=false&price_change_percentage=7d"
    )
    btc_30d  = _coingecko("/coins/bitcoin/market_chart?vs_currency=usd&days=30&interval=daily")
    eth_30d  = _coingecko("/coins/ethereum/market_chart?vs_currency=usd&days=30&interval=daily")
    global_d = _coingecko("/global")

    parts = [f"Crypto Weekly — {TODAY}\n"]

    if fg_val is not None:
        parts.append(f"Fear & Greed: {fg_val} ({fg_label})")

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

    parts.append("\nSource: CoinGecko · alternative.me")
    parts.append("Not investment advice.")
    parts.append("\n#Crypto #Bitcoin #DataEngineering")
    return "\n".join(parts)[:280]


def build_caption_oilgas():
    cl_price, cl_ret = _yf_5d("CL=F")
    ng_price, ng_ret = _yf_5d("NG=F")
    xle, xle_ret     = _yf_5d("XLE")
    slb, slb_ret     = _yf_5d("SLB")

    parts = [f"Energy Weekly — {TODAY}\n"]
    if cl_price is not None:
        parts.append(f"WTI Crude: ${cl_price:.2f}  ({cl_ret:+.1f}% 5d)")
    if ng_price is not None:
        parts.append(f"Henry Hub: ${ng_price:.3f}/MMBtu  ({ng_ret:+.1f}% 5d)")
    if xle_ret is not None:
        parts.append(f"XLE ETF: {xle_ret:+.1f}% 5d")
    if slb_ret is not None:
        parts.append(f"SLB: {slb_ret:+.1f}% 5d")
    if cl_price and ng_price:
        ratio = cl_price / (ng_price * 6)
        parts.append(f"Oil/Gas BTU ratio: {ratio:.1f}x")
    parts.append("\nSource: EIA via FRED · Yahoo Finance (NYMEX)")
    parts.append("Not investment advice.")
    parts.append("\n#Energy #OilGas #DataEngineering")
    return "\n".join(parts)[:280]


def build_caption_brokerage():
    spy_price, spy_ret = _yf_5d("SPY")
    vix, _             = _yf_5d("^VIX")
    gs,   gs_ret       = _yf_5d("GS")
    ms,   ms_ret       = _yf_5d("MS")
    schw, schw_ret     = _yf_5d("SCHW")
    ten_y              = _fred_latest("DGS10")  # 10Y Treasury — Federal Reserve

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
    parts.append("\nSource: Yahoo Finance · FRED (Federal Reserve)")
    parts.append("Not investment advice.")
    parts.append("\n#Finance #Brokerage #DataEngineering")
    return "\n".join(parts)[:280]


def build_caption_compliance():
    # AP = SEC Administrative Proceedings (actual enforcement orders, filed by SEC)
    # AAE = Accounting and Auditing Enforcement Releases
    # 8-K keyword = companies self-disclosing receipt of SEC notice to investors
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
    parts.append("\n#Compliance #SEC #DataEngineering")
    return "\n".join(parts)[:280]


def build_caption_betting():
    _, dkng = _yf_5d("DKNG"); _, penn = _yf_5d("PENN")
    _, flut = _yf_5d("FLUT"); _, betz = _yf_5d("BETZ")
    _, spy  = _yf_5d("SPY")
    m = datetime.now().month
    season = ("NBA Finals · MLB · Stanley Cup" if m == 6 else
              "NFL Playoffs · NBA · NHL"        if m in (1, 2) else
              "NFL Season · MLB · NBA"          if m in (9, 10) else
              "NFL · NBA · NHL · MLB")
    parts = [f"Betting Sector — {TODAY}\n"]
    tickers = [("DKNG", dkng), ("PENN", penn), ("FLUT", flut), ("BETZ ETF", betz)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    parts.append(f"\nActive: {season}")
    parts.append("\nSource: Yahoo Finance")
    parts.append("Not investment advice.")
    parts.append("\n#SportsBetting #Finance #DataEngineering")
    return "\n".join(parts)[:280]


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
    parts.append("\n#Gaming #VideoGames #DataEngineering")
    return "\n".join(parts)[:280]


def build_caption_ecommerce():
    _, amzn = _yf_5d("AMZN"); _, shop = _yf_5d("SHOP")
    _, etsy = _yf_5d("ETSY"); _, spy  = _yf_5d("SPY")
    parts = [f"E-Commerce Sector — {TODAY}\n"]
    tickers = [("AMZN", amzn), ("SHOP", shop), ("ETSY", etsy)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    parts.append("\nConsumer sentiment (FRED UMCSENT) in card.")
    parts.append("\nSource: Yahoo Finance · FRED (Federal Reserve)")
    parts.append("Not investment advice.")
    parts.append("\n#Ecommerce #Retail #DataEngineering")
    return "\n".join(parts)[:280]


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
    parts.append("\n#Streaming #Media #DataEngineering")
    return "\n".join(parts)[:280]


def build_caption_solar():
    _, fslr = _yf_5d("FSLR"); _, enph = _yf_5d("ENPH")
    _, tan  = _yf_5d("TAN");  _, spy  = _yf_5d("SPY")
    parts = [f"Clean Energy Sector — {TODAY}\n"]
    tickers = [("FSLR", fslr), ("ENPH", enph), ("TAN ETF", tan)]
    for sym, ret in tickers:
        if ret is not None:
            parts.append(f"{sym}: {ret:+.1f}%")
    if spy is not None:
        parts.append(f"SPY: {spy:+.1f}%")
    parts.append("\nWTI crude context in card (EIA via FRED).")
    parts.append("\nSource: Yahoo Finance · FRED (Federal Reserve)")
    parts.append("Not investment advice.")
    parts.append("\n#Solar #CleanEnergy #DataEngineering")
    return "\n".join(parts)[:280]


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
            req = urllib.request.Request(url, headers={"User-Agent": "CleanMetrics/1.0"})
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
    parts.append("\n#Weather #Climate #DataEngineering")
    return "\n".join(parts)[:280]


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

    # v2 Client — for creating tweets
    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    # v1.1 API — for media upload (still required even in 2026)
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

    print(f"Card ready: {card}")
    return card


def post_to_x(vertical, dry_run=False):
    # 1. Generate card
    card_path = run_generator(vertical)

    # 2. Build caption
    print(f"Building caption for {vertical}...")
    caption = CAPTION_BUILDERS[vertical]()
    print(f"\n--- CAPTION ({len(caption)} chars) ---\n{caption}\n---\n")

    if dry_run:
        print(f"DRY RUN — card: {card_path}")
        print("No post made. Remove --dry-run to post live.")
        return

    # 3. Auth
    client, api_v1 = get_clients()

    # 4. Upload media (v1.1)
    print("Uploading image...")
    media = api_v1.media_upload(filename=str(card_path))
    print(f"Media ID: {media.media_id}")

    # 5. Post tweet (v2)
    print("Posting tweet...")
    response = client.create_tweet(text=caption, media_ids=[media.media_id])
    tweet_id = response.data["id"]
    print(f"Posted: https://x.com/Mboya_Jeffers/status/{tweet_id}")

    # 6. Log + notify
    log_post(vertical, tweet_id, card_path, caption)
    notify_telegram(
        f"✓ Posted [{vertical}] — {TODAY}\n"
        f"https://x.com/Mboya_Jeffers/status/{tweet_id}"
    )

    return tweet_id

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
        notify_telegram(f"✗ Post FAILED [{args.vertical}] — {NOW}\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
