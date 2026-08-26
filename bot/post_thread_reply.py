#!/usr/bin/env python3
"""
X Thread Reply Bot — @Mboya_Jeffers
Posts affiliate thread reply 90 minutes after the main tweet.

The 90-min gap is intentional: it lets the main tweet accumulate early
engagement before the reply appears. Simultaneous replies suppress the
main tweet's organic reach.

Usage:
    python3 post_thread_reply.py worldcup            # reads tweet_id from log
    python3 post_thread_reply.py betting <tweet_id>  # explicit tweet_id override
    python3 post_thread_reply.py crypto --dry-run    # preview text, no API call

FTC compliance: #ad is included in all affiliate thread replies.

Cron (90 min after each morning post + worldcup):
    Run post.py first, then post_thread_reply.py 90 min later.
    See crontab for schedule.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Add bot dir to path so we can import affiliate_config
BOT_DIR  = Path(__file__).parent.resolve()
LOG_PATH = BOT_DIR / "post_log.json"
TODAY    = datetime.now().strftime("%Y-%m-%d")
NOW      = datetime.now().strftime("%Y-%m-%d %H:%M")

sys.path.insert(0, str(BOT_DIR))
from affiliate_config import (  # noqa: E402
    THREAD_REPLIES, BIO_LINK, AFFILIATE_SITE_URL,
    TRADINGVIEW_AFFILIATE_URL, KRAKEN_AFFILIATE_URL,
    BETWAY_AFFILIATE_URL, BETMGM_AFFILIATE_URL, HARDROCKBET_AFFILIATE_URL, CAESARS_AFFILIATE_URL,
    WEBULL_REFERRAL_URL, MOOMOO_REFERRAL_URL, ROBINHOOD_REFERRAL_URL,
)

# Sponsor URLs that can ever appear inside a thread reply. Used below to check
# for a real disclosure requirement based on what's actually IN the text,
# rather than blanket vertical membership in REQUIRES_DISCLOSURE — that set is
# about the main caption's CTA machinery (see affiliate_config.py) and no
# longer implies the *thread reply* for that same vertical carries a sponsor
# (finance/brokerage/crypto's replies are deliberately neutral now — the
# sponsor mention, if any, lives once in the main caption, not repeated here).
_ALL_SPONSOR_URLS = [
    TRADINGVIEW_AFFILIATE_URL, KRAKEN_AFFILIATE_URL,
    BETWAY_AFFILIATE_URL, BETMGM_AFFILIATE_URL, HARDROCKBET_AFFILIATE_URL, CAESARS_AFFILIATE_URL,
    WEBULL_REFERRAL_URL, MOOMOO_REFERRAL_URL, ROBINHOOD_REFERRAL_URL,
]
from verify import tweet_weighted_length  # noqa: E402


# ─── DYNAMIC THREAD REPLY BUILDERS ───────────────────────────────────────────

def _api_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def build_worldcup_thread_reply() -> str:
    """
    Fetch live PENN + FLUT returns since WC kickoff and build the worldcup thread reply.
    All figures are live — never stale. Called at post time.
    """
    import yfinance as yf
    from affiliate_config import (
        BIO_LINK, WC_REPORT_PRICE, GUMROAD_WC_REPORT_URL,
        AFFILIATE_SITE_URL, _gumroad_wc_live,
    )

    penn_ret = None
    BASELINE = "2026-06-11"
    try:
        hist = yf.Ticker("PENN").history(start=BASELINE)
        if not hist.empty and len(hist) >= 2:
            c = hist["Close"].dropna().tolist()
            penn_ret = round((c[-1] - c[0]) / c[0] * 100, 1)
    except Exception:
        pass

    penn_str = f"$PENN {penn_ret:+.1f}% since kickoff" if penn_ret is not None else "$PENN through the tournament"

    # No sportsbook sponsor tag on X (gambling banned from paid partnerships
    # Feb 2026) — sportsbook comparison + real affiliate links live on the
    # site only. GUMROAD_WC_REPORT_URL is a first-party product, not a
    # third-party affiliate, so no #ad is needed for that line alone.
    reply = f"I track sportsbook stocks daily. {penn_str}.\n\n"
    if _gumroad_wc_live:
        reply += f"Full report {WC_REPORT_PRICE} → {GUMROAD_WC_REPORT_URL}\n\n"
    else:
        reply += f"Full report → {BIO_LINK}\n\n"

    reply += f"Full sportsbook comparison → {AFFILIATE_SITE_URL}"
    return reply


def build_crypto_thread_reply() -> str:
    """Fetch live MVRV, F&G, Aave TVL and build the crypto thread reply.
    All values are live — never stale. Called at post time by post_thread_reply.py.
    """
    mvrv_val  = mvrv_label = fg_val = fg_label = aave_tvl = aave_7d = None

    # MVRV Ratio — CoinMetrics community tier (no key required)
    try:
        data = _api_get(
            "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
            "?assets=btc&metrics=CapMVRVCur&page_size=5"
        )
        entries = [(r["time"], float(r["CapMVRVCur"])) for r in data.get("data", []) if r.get("CapMVRVCur")]
        if entries:
            mvrv_val = entries[-1][1]
            if mvrv_val > 3.0:
                mvrv_label = "OVERVALUED"
            elif mvrv_val > 1.5:
                mvrv_label = "FAIR VALUE"
            elif mvrv_val > 1.0:
                mvrv_label = "NEUTRAL"
            else:
                mvrv_label = "UNDERVALUED"
        time.sleep(2)
    except Exception:
        pass

    # Fear & Greed — alternative.me
    try:
        data     = _api_get("https://api.alternative.me/fng/?limit=1")
        fg_val   = int(data["data"][0]["value"])
        fg_label = data["data"][0]["value_classification"]
        time.sleep(1)
    except Exception:
        pass

    # Aave V3 TVL — DeFi Llama
    try:
        data = _api_get("https://api.llama.fi/protocol/aave-v3")
        tvl_series = data.get("tvl", [])
        if len(tvl_series) >= 8:
            now_tvl  = tvl_series[-1]["totalLiquidityUSD"]
            week_tvl = tvl_series[-8]["totalLiquidityUSD"]
            aave_tvl = now_tvl / 1e9
            aave_7d  = (now_tvl - week_tvl) / week_tvl * 100
    except Exception:
        pass

    # Build reply text
    lines = []

    if mvrv_val is not None:
        lines.append(f"BTC MVRV at {mvrv_val:.2f} ({mvrv_label}) — market vs realized value.")
    if fg_val is not None:
        lines.append(f"Fear & Greed: {fg_val} ({fg_label}).", )
    if aave_tvl is not None and aave_7d is not None:
        lines.append(f"Aave V3 TVL: ${aave_tvl:.2f}B ({aave_7d:+.1f}% 7d).")

    if not lines:
        lines.append("Live on-chain data — full report below.")

    # No crypto-exchange sponsor tag on X (banned from paid partnerships Mar
    # 2026) — Kraken's affiliate link lives on the site only now. The white
    # glove report below is a first-party product, not a third-party
    # affiliate, so no #ad is needed for this reply.
    reply = "\n".join(lines)
    reply += (
        "\n\nWhite glove: full on-chain report, signal read, macro overlay, DeFi risk.\n"
        "$99 report / $299 + signal / $599 + monthly call\n"
        f"{BIO_LINK}"
    )
    return reply


# ─── LOG HELPERS ─────────────────────────────────────────────────────────────

def load_log():
    if not LOG_PATH.exists():
        return {"posts": []}
    try:
        return json.loads(LOG_PATH.read_text())
    except Exception:
        return {"posts": []}


def save_log(data):
    LOG_PATH.write_text(json.dumps(data, indent=2))


PENDING_STALE_HOURS = 24  # thread replies are meant to go out ~90 min after
# the main post — an entry still unreplied a day later isn't "pending," it's
# abandoned. Found 2026-08-24: a July 9 oilgas launch tweet had sat with
# thread_pending=True/thread_posted=False for 6+ weeks (thread replies never
# actually worked until today) and was being returned ahead of today's real
# post — replying to a 6-week-old tweet now would look broken, not current.


def find_pending(vertical):
    """Return the most recent, still-fresh log entry with thread_pending=True,
    thread_posted=False. Entries older than PENDING_STALE_HOURS are skipped."""
    data = load_log()
    # Search newest first
    for entry in reversed(data["posts"]):
        if not (entry.get("vertical") == vertical
                and entry.get("thread_pending") is True
                and entry.get("thread_posted") is False):
            continue
        try:
            age_hours = (datetime.now() - datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M")).total_seconds() / 3600
        except Exception:
            age_hours = None
        if age_hours is not None and age_hours > PENDING_STALE_HOURS:
            continue
        return entry, data
    return None, data


def mark_thread_posted(data, tweet_id, reply_id):
    for entry in data["posts"]:
        if entry.get("tweet_id") == str(tweet_id):
            entry["thread_posted"]   = True
            entry["thread_tweet_id"] = str(reply_id)
            entry["thread_timestamp"] = NOW
            break
    save_log(data)


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


# ─── TWEEPY AUTH ─────────────────────────────────────────────────────────────

def get_client():
    try:
        import tweepy
    except ImportError:
        print("ERROR: tweepy not installed. Run: pip install tweepy")
        sys.exit(1)

    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing  = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="X Thread Reply Bot — @Mboya_Jeffers")
    parser.add_argument("vertical",
                        choices=list(THREAD_REPLIES.keys()),
                        help="Vertical to post thread reply for")
    parser.add_argument("tweet_id", nargs="?", default=None,
                        help="Explicit tweet ID (overrides log lookup)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview reply text, no API call")
    args = parser.parse_args()

    vertical = args.vertical

    # 1. Get reply text
    reply_text = THREAD_REPLIES.get(vertical)
    if reply_text is None:
        print(f"No thread reply configured for [{vertical}] — skipping.")
        sys.exit(0)

    # 1a. Dynamic builder — fetch live data instead of using static string
    if reply_text == "__DYNAMIC__":
        if vertical == "crypto":
            print(f"Building live [{vertical}] thread reply from APIs...")
            reply_text = build_crypto_thread_reply()
            print(f"Live reply built ({len(reply_text)} chars).")
        elif vertical == "worldcup":
            print(f"Building live [{vertical}] thread reply (live stock returns)...")
            reply_text = build_worldcup_thread_reply()
            print(f"Live reply built ({len(reply_text)} chars).")
        else:
            print(f"ERROR: __DYNAMIC__ sentinel set for [{vertical}] but no builder exists.", file=sys.stderr)
            sys.exit(1)

    # 1b. Placeholder guard — never publish unfilled affiliate/URL placeholders.
    # affiliate_config uses [BRACKETED] tokens for pending URLs. If any survive
    # into the reply text, abort rather than post broken links to the timeline.
    import re
    placeholders = re.findall(r"\[[A-Z0-9_]+\]", reply_text)
    if placeholders:
        msg = (f"Thread reply [{vertical}] BLOCKED — unfilled placeholders: "
               f"{', '.join(sorted(set(placeholders)))}. "
               f"Fill them in affiliate_config.py before this thread can post.")
        print(f"ERROR: {msg}", file=sys.stderr)
        notify_telegram(f"Thread reply SKIPPED [{vertical}] — {NOW}\n{msg}")
        sys.exit(0)

    # 1c. Length + disclosure guard — this path had zero validation before
    # posting (unlike post.py's main captions, which go through verify.py).
    # Found live 2026-08-24: every static/dynamic reply except media/finance/
    # brokerage was 100-220 chars over X's 280 limit, never caught because no
    # thread reply had ever actually been posted before that point.
    problems = []
    weighted = tweet_weighted_length(reply_text)
    if weighted > 280:
        problems.append(f"{weighted}/280 weighted chars")
    _live_sponsor_present = any(
        url in reply_text for url in _ALL_SPONSOR_URLS if not url.startswith("[")
    )
    if _live_sponsor_present and "#ad" not in reply_text.lower():
        problems.append("#ad MISSING (FTC required)")
    if problems:
        msg = f"Thread reply [{vertical}] BLOCKED — {'; '.join(problems)}."
        print(f"ERROR: {msg}", file=sys.stderr)
        notify_telegram(f"Thread reply SKIPPED [{vertical}] — {NOW}\n{msg}")
        sys.exit(0)

    # 2. Find tweet_id
    if args.tweet_id:
        tweet_id = args.tweet_id
        log_data = load_log()
        pending_entry = None
        for entry in reversed(log_data["posts"]):
            if entry.get("tweet_id") == str(tweet_id):
                pending_entry = entry
                break
    else:
        pending_entry, log_data = find_pending(vertical)
        if pending_entry is None:
            print(f"No pending thread reply found for [{vertical}] in post_log.json.")
            print("Either the main tweet hasn't been posted yet, or the thread was already sent.")
            sys.exit(0)
        tweet_id = pending_entry["tweet_id"]

    print(f"\n--- THREAD REPLY ({vertical}) ---")
    print(f"Replying to tweet ID: {tweet_id}")
    print(f"\n{reply_text}\n")
    print(f"--- ({len(reply_text)} raw / {weighted} weighted chars) ---\n")

    if args.dry_run:
        print("DRY RUN — no API call made. Remove --dry-run to post live.")
        return

    # 3. Post reply
    client = get_client()

    try:
        response = client.create_tweet(
            text=reply_text,
            in_reply_to_tweet_id=tweet_id
        )
        reply_id = response.data["id"]
        url = f"https://x.com/Mboya_Jeffers/status/{reply_id}"
        print(f"Thread reply posted: {url}")

        # 4. Update log
        if pending_entry is not None:
            mark_thread_posted(log_data, tweet_id, reply_id)
            print(f"Log updated: thread_posted=True for tweet {tweet_id}")

        # 5. Notify
        notify_telegram(
            f"Thread reply posted [{vertical}] — {NOW}\n{url}"
        )

    except Exception as e:
        print(f"ERROR posting thread reply: {e}", file=sys.stderr)
        notify_telegram(f"Thread reply FAILED [{vertical}] — {NOW}\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
