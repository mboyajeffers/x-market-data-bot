#!/usr/bin/env python3
"""
Engagement readback — @Mboya_Jeffers X Bot

post_log.json records what was posted, never how it performed. This script
closes that gap: pulls public_metrics (impressions, likes, replies, retweets,
quotes, bookmarks) for every tweet_id already logged, and writes them back
into post_log.json. Run on a schedule (GitHub Actions or local cron,
matching the bot's existing automation — see .github/workflows/).

Batches tweet_ids into groups of 100 (tweepy.Client.get_tweets max) to
minimize billed API calls — each GET request costs $0.005 regardless of how
many of the 100 allowed IDs are included, so one batched call for 40 tweets
costs the same as one call for 1.

Usage:
    python3 fetch_engagement.py              # update all logged tweets
    python3 fetch_engagement.py --since 7    # only tweets from the last N days
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BOT_DIR  = Path(__file__).parent.resolve()
LOG_PATH = BOT_DIR / "post_log.json"

sys.path.insert(0, str(BOT_DIR))


def get_client():
    """Reuses the same v2 client/auth pattern as post.py's get_clients()."""
    try:
        import tweepy
    except ImportError:
        print("ERROR: tweepy not installed. Run: pip install tweepy")
        sys.exit(1)

    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        print("Run: source ~/.x_bot_env")
        sys.exit(1)

    # GET /2/tweets (read) returned 401 under plain OAuth 1.0a user-context
    # auth even though writes work fine with the same keys — passing the
    # bearer token too lets tweepy fall back to App-only auth for read
    # endpoints that need it under this app's permission level.
    return tweepy.Client(
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def load_log():
    if not LOG_PATH.exists():
        return {"posts": []}
    return json.loads(LOG_PATH.read_text())


def save_log(data):
    LOG_PATH.write_text(json.dumps(data, indent=2))


def _collect_ids(posts, since_days=None):
    """Every tweet_id worth checking — main post + thread reply, if posted."""
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now() - timedelta(days=since_days)

    ids = set()
    for entry in posts:
        if cutoff is not None:
            try:
                ts = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M")
                if ts < cutoff:
                    continue
            except Exception:
                pass
        if entry.get("tweet_id"):
            ids.add(entry["tweet_id"])
        if entry.get("thread_tweet_id"):
            ids.add(entry["thread_tweet_id"])
    return ids


def _batched(seq, size=100):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_metrics(client, tweet_ids):
    """Returns {tweet_id: public_metrics_dict}. Batches into groups of 100."""
    metrics = {}
    for batch in _batched(tweet_ids, 100):
        try:
            resp = client.get_tweets(ids=batch, tweet_fields=["public_metrics"])
        except Exception as e:
            print(f"WARN: batch of {len(batch)} failed: {e}")
            continue
        if not resp.data:
            continue
        for tweet in resp.data:
            metrics[str(tweet.id)] = tweet.public_metrics
    return metrics


def apply_metrics(posts, metrics):
    """Writes fetched metrics back onto each post_log entry in place.
    Returns count of entries updated."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    updated = 0
    for entry in posts:
        tid = entry.get("tweet_id")
        if tid and tid in metrics:
            entry["public_metrics"] = metrics[tid]
            entry["metrics_fetched_at"] = now
            updated += 1
        ttid = entry.get("thread_tweet_id")
        if ttid and ttid in metrics:
            entry["thread_public_metrics"] = metrics[ttid]
            entry["thread_metrics_fetched_at"] = now
            updated += 1
    return updated


def main():
    parser = argparse.ArgumentParser(description="Fetch X engagement metrics for logged posts")
    parser.add_argument("--since", type=int, default=None,
                        help="Only refresh posts from the last N days (default: all)")
    args = parser.parse_args()

    client = get_client()
    log = load_log()
    posts = log.get("posts", [])
    if not posts:
        print("post_log.json has no entries — nothing to fetch.")
        return

    ids = _collect_ids(posts, since_days=args.since)
    if not ids:
        print("No tweet_ids found in range.")
        return

    print(f"Fetching public_metrics for {len(ids)} tweet(s)...")
    metrics = fetch_metrics(client, ids)
    updated = apply_metrics(posts, metrics)
    save_log(log)
    print(f"Updated {updated} post_log entries with real engagement data "
          f"({len(metrics)}/{len(ids)} tweet_ids resolved).")


if __name__ == "__main__":
    main()
