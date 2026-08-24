#!/usr/bin/env python3
"""
spot_check_xbot.py — Fortune 500-grade QA gate for X bot posts.

Usage:
  python REVENUE/X/scripts/spot_check_xbot.py crypto           # check staged crypto
  python REVENUE/X/scripts/spot_check_xbot.py crypto --live    # + live API validation
  python REVENUE/X/scripts/spot_check_xbot.py all              # check all staged entries

Exit 0 = PASS (no CRITICALs in any checked vertical)
Exit 1 = FAIL (any CRITICAL in any checked vertical)
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

# Resolve bot dir for affiliate_config import (scripts/ → bot/)
BOT_DIR    = Path(__file__).parent.parent / "bot"
sys.path.insert(0, str(BOT_DIR))
import affiliate_config  # noqa: E402

STAGING_PATH = BOT_DIR / "staging.json"
TODAY        = date.today().isoformat()

# Verticals that must have a non-None thread reply
THREAD_REPLY_REQUIRED = {"crypto", "worldcup", "betting", "cannabis"}

# Crypto card visual constants (from generate_crypto_x_card.py)
CARD_BG       = (10, 14, 20)       # #0a0e14
CRYPTO_ACCENT = (168, 85, 247)     # #a855f7
ACCENT_TOL    = 40

# ── Output state ─────────────────────────────────────────────────────────────
_criticals: list[str] = []
_warnings:  list[str] = []
_infos:     list[str] = []


def crit(msg: str) -> None:
    _criticals.append(msg)
    print(f"[CRITICAL]  {msg}")


def warn(msg: str) -> None:
    _warnings.append(msg)
    print(f"[WARN]      {msg}")


def info(msg: str) -> None:
    _infos.append(msg)
    print(f"[INFO]      {msg}")


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_mvrv() -> tuple:
    url = (
        "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        "?assets=btc&metrics=CapMVRVCur&page_size=30"
    )
    data = _get(url)
    entries = [
        (r["time"], float(r["CapMVRVCur"]))
        for r in data.get("data", [])
        if r.get("CapMVRVCur") is not None
    ]
    if not entries:
        return None, None
    return entries[-1][1], entries[-1][0]


def fetch_fear_greed() -> tuple:
    data  = _get("https://api.alternative.me/fng/?limit=1")
    entry = data["data"][0]
    return int(entry["value"]), entry["value_classification"]


# ── Card image checks (Pillow) ────────────────────────────────────────────────

def check_card_image(card_path: Path, vertical: str) -> None:
    try:
        from PIL import Image
    except ImportError:
        warn("Pillow not installed — skipping image content checks (pip install Pillow)")
        return

    try:
        img = Image.open(card_path).convert("RGB")
    except Exception as e:
        crit(f"Cannot open card image with Pillow: {e}")
        return

    w, h   = img.size
    pixels = img.load()
    info(f"Card dimensions: {w}x{h}px")

    # C9: Landscape orientation
    if w <= h:
        crit(f"Card is not landscape ({w}x{h}) — X displays cards in landscape, this will render incorrectly")

    # W3: Bar chart region content — sample left panel (bar chart lives here)
    # Scaled from 1200x675 reference dimensions
    scale_x = w / 1200
    scale_y = h / 675
    x0, x1 = int(30  * scale_x), int(400 * scale_x)
    y0, y1 = int(100 * scale_y), int(575 * scale_y)
    sample  = [(random.randint(x0, x1), random.randint(y0, y1)) for _ in range(100)]
    content = sum(
        1 for (px, py) in sample
        if sum(abs(pixels[px, py][c] - CARD_BG[c]) for c in range(3)) > 40
    )
    if content < 5:
        warn(
            f"Bar chart region appears empty ({content}/100 sampled pixels differ from background) "
            "— possible render failure"
        )
    else:
        info(f"Card content: {content}/100 bar-chart-region pixels have rendered content")

    # W4: Brand accent color detection (crypto only)
    if vertical == "crypto":
        step_x = max(1, w // 60)
        step_y = max(1, h // 60)
        accent_count = sum(
            1
            for gx in range(0, w, step_x)
            for gy in range(0, h, step_y)
            if all(abs(pixels[gx, gy][c] - CRYPTO_ACCENT[c]) <= ACCENT_TOL for c in range(3))
        )
        if accent_count < 5:
            warn(
                f"Crypto accent color #a855f7 not detected in pixel sampling "
                f"({accent_count} matching pixels) — card may not have rendered correctly"
            )
        else:
            info(f"Brand color #a855f7 detected ({accent_count} matching pixels on 60×60 grid)")


# ── Live thread reply cross-check ─────────────────────────────────────────────

def check_thread_reply_live(thread_reply: str) -> None:
    """C13: Compare MVRV + F&G values in thread reply against live data."""
    print("\n  --- Live thread reply cross-check ---")
    try:
        live_mvrv, _ = fetch_mvrv()
        time.sleep(3)
        live_fg, fg_label = fetch_fear_greed()

        all_nums        = [float(x) for x in re.findall(r'\d+\.?\d*', thread_reply)]
        mvrv_candidates = [n for n in all_nums if 0.5 <= n <= 5.0]
        fg_candidates   = [int(n) for n in all_nums if 1 <= n <= 100 and float(n) == int(n)]

        if live_mvrv and mvrv_candidates:
            reply_mvrv = mvrv_candidates[0]
            diff_pct   = abs(reply_mvrv - live_mvrv) / live_mvrv * 100
            if diff_pct > 10:
                crit(
                    f"Thread reply MVRV is stale: shows {reply_mvrv}, live is {live_mvrv:.2f} "
                    f"({diff_pct:.1f}% off) — update THREAD_REPLIES['crypto'] in affiliate_config.py"
                )
            else:
                info(f"Thread reply MVRV: {reply_mvrv} vs live {live_mvrv:.2f} — within tolerance")
        elif live_mvrv and not mvrv_candidates:
            warn("Thread reply has no MVRV-range number (0.5–5.0) — live on-chain data not reflected")

        if live_fg is not None and fg_candidates:
            reply_fg = fg_candidates[0]
            diff_pct = abs(reply_fg - live_fg) / max(live_fg, 1) * 100
            if diff_pct > 15:
                crit(
                    f"Thread reply F&G is stale: shows {reply_fg}, live is {live_fg} ({fg_label}) "
                    f"({diff_pct:.1f}% off) — update THREAD_REPLIES['crypto'] in affiliate_config.py"
                )
            else:
                info(f"Thread reply F&G: {reply_fg} vs live {live_fg} ({fg_label}) — within tolerance")
        elif live_fg is not None and not fg_candidates:
            warn("Thread reply has no F&G-range integer (1–100) — live sentiment not reflected")

    except Exception as e:
        warn(f"Live thread reply cross-check failed: {e}")


# ── Check one staged vertical ─────────────────────────────────────────────────

def check_vertical(vertical: str, entry: dict, live: bool = False) -> None:
    caption     = entry.get("caption", "")
    card_path_s = entry.get("card_path", "")
    preview_ts  = entry.get("preview_time", "")
    char_count  = entry.get("char_count", len(caption))

    # Staging age info
    if preview_ts:
        try:
            pt      = datetime.fromisoformat(preview_ts)
            age_min = (datetime.now() - pt).total_seconds() / 60
            info(f"Staging entry: {age_min:.0f} min old (previewed {preview_ts[:16]})")
            if age_min > 30:
                warn(
                    f"Staging is {age_min:.0f} min old — xbot post rejects entries >30 min; "
                    "re-run: xbot preview " + vertical
                )
        except Exception:
            pass

    # ── CRITICAL checks ───────────────────────────────────────────────────────

    # C2: Caption length
    if char_count > 280 or len(caption) > 280:
        crit(f"Caption exceeds X 280-char limit: {max(char_count, len(caption))} chars")

    # C3: No placeholder in caption
    cap_ph = list(set(re.findall(r'\[[A-Z0-9_]{3,}\]', caption)))
    if cap_ph:
        crit(f"Unfilled placeholder(s) in caption: {cap_ph}")

    # C4 + C5: Thread reply checks
    thread_reply = affiliate_config.THREAD_REPLIES.get(vertical)
    # "__DYNAMIC__" means reply is built live from APIs at post time — counts as configured
    is_dynamic = (thread_reply == "__DYNAMIC__")
    if vertical in THREAD_REPLY_REQUIRED and not thread_reply:
        crit(f"THREAD_REPLIES['{vertical}'] is None/empty — no follow-up post will go out")
    if is_dynamic:
        info(f"Thread reply [{vertical}]: DYNAMIC — built live from APIs at post time (MVRV, F&G, Aave TVL)")
    elif thread_reply:
        reply_ph = list(set(re.findall(r'\[[A-Z0-9_]{3,}\]', thread_reply)))
        if reply_ph:
            crit(f"Unfilled placeholder(s) in thread reply: {reply_ph}")
        info(f"Thread reply: {len(thread_reply)} chars")

    # C6–C9: Card checks
    if not card_path_s:
        crit("No card_path in staging entry")
    else:
        card_path = Path(card_path_s)
        if not card_path.exists():
            crit(f"Card file not found at stored path: {card_path}")
        else:
            # C7: Generated today
            card_date = card_path.stem.split("_")[-1]  # e.g. crypto_x_card_2026-07-04
            if card_date != TODAY:
                crit(f"Card is from {card_date} — not today ({TODAY}). Re-run: xbot preview {vertical}")

            # C8: File size
            card_kb = card_path.stat().st_size / 1024
            if card_kb < 50:
                crit(f"Card too small: {card_kb:.1f}KB (expected >50KB — likely a failed render)")
            elif card_kb > 8192:
                crit(f"Card too large: {card_kb:.1f}KB (X media limit ~8MB)")
            else:
                info(f"Card: {card_kb:.0f}KB → {card_path.name}")

            # C9 + W3 + W4: Image content checks
            check_card_image(card_path, vertical)

    # C10: CTA matches affiliate_config exactly
    expected_cta = affiliate_config.VERTICAL_CTA.get(vertical, "")
    if expected_cta and expected_cta not in caption:
        crit(
            f"CTA mismatch — current affiliate_config value:\n"
            f"  '{expected_cta}'\n"
            f"  This exact string is not in the caption. "
            f"Re-run xbot preview after updating affiliate_config."
        )
    elif expected_cta:
        display_cta = expected_cta[:70] + "..." if len(expected_cta) > 70 else expected_cta
        info(f"CTA verified: '{display_cta}'")

    # C11: FTC compliance
    if vertical in affiliate_config.REQUIRES_DISCLOSURE:
        if "#ad" not in caption.lower():
            crit(f"FTC violation: '{vertical}' requires #ad in main caption per REQUIRES_DISCLOSURE — not found")

    # C12: worldcup CTA placeholder guard
    if vertical == "worldcup":
        wc_cta = affiliate_config.VERTICAL_CTA.get("worldcup", "")
        if re.search(r'\[[A-Z0-9_]{3,}\]', wc_cta):
            crit(
                "worldcup VERTICAL_CTA contains an unfilled placeholder — "
                "set GUMROAD_WC_REPORT_URL in affiliate_config.py before posting"
            )

    # ── WARNING checks ────────────────────────────────────────────────────────

    # W1: Caption truncation risk
    cap_len = max(char_count, len(caption))
    if 261 <= cap_len <= 280:
        warn(f"Caption is {cap_len}/280 chars — CTA is at risk of truncation")
        # Verify CTA + source survived the slice
        sliced = caption[:280]
        if expected_cta and expected_cta not in sliced:
            warn("CTA was cut by 280-char truncation — not present in final 280-char slice")
        if "Source:" not in sliced and "Not investment advice" not in sliced:
            warn("Source/disclaimer line may have been cut by 280-char truncation")
    else:
        info(f"Caption: {cap_len}/280 chars ({280 - cap_len} remaining)")

    # W2: Crypto data completeness
    if vertical == "crypto":
        has_fg    = bool(re.search(r'Fear\s*&\s*Greed:\s*\d+', caption, re.IGNORECASE))
        has_price = bool(re.search(r'(?:\d+\.?\d+%|\$\d+\.?\d+[TB]?|\bdom:)', caption))
        if not has_fg:
            warn("Fear & Greed value not in caption — sentiment fetch may have failed")
        if not has_price:
            warn("No price/return/dominance data in caption — CoinGecko may have silently failed")
        if has_fg and not has_price:
            warn("Only F&G present — all price data absent (F&G alone is insufficient for a data post)")

    # W5: OKX funding rate present (crypto) — replaces old Binance geo-block check
    if vertical == "crypto":
        if "funding" not in caption.lower() and "OI" not in caption:
            warn("Funding rate / OI absent from caption — OKX fetch may have failed")

    # W6: SIGNAL_PRICE drift
    if affiliate_config.SIGNAL_PRICE != "$300/mo":
        info(
            f"SIGNAL_PRICE is '{affiliate_config.SIGNAL_PRICE}' "
            "(not $300/mo) — verify thread reply pricing is current"
        )

    # ── Live cross-check ──────────────────────────────────────────────────────
    if live and vertical == "crypto":
        if is_dynamic:
            # Build the dynamic reply live and cross-check it
            sys.path.insert(0, str(BOT_DIR / "bot"))
            try:
                from post_thread_reply import build_crypto_thread_reply
                live_reply = build_crypto_thread_reply()
                info(f"Dynamic thread reply built live ({len(live_reply)} chars) — cross-checking values...")
                check_thread_reply_live(live_reply)
            except Exception as e:
                warn(f"Dynamic thread reply builder failed during spot check: {e}")
        elif thread_reply:
            check_thread_reply_live(thread_reply)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Spot check X bot staged posts")
    parser.add_argument("vertical", nargs="+", help="Vertical name(s) or 'all'")
    parser.add_argument("--live", action="store_true", help="Re-fetch live data for cross-validation")
    args = parser.parse_args()

    # Load staging
    if not STAGING_PATH.exists():
        print(f"[CRITICAL]  staging.json not found: {STAGING_PATH}")
        sys.exit(1)

    staging = json.loads(STAGING_PATH.read_text())
    posts   = {p["vertical"]: p for p in staging.get("posts", [])}

    targets = list(posts.keys()) if args.vertical == ["all"] else args.vertical

    any_critical = False

    for vertical in targets:
        _criticals.clear()
        _warnings.clear()
        _infos.clear()

        print(f"\n=== SPOT CHECK: X Bot — {vertical} — {TODAY} ===\n")

        # C1: Staging entry exists
        if vertical not in posts:
            crit(f"No staged entry for '{vertical}' — run: xbot preview {vertical}")
        else:
            check_vertical(vertical, posts[vertical], live=args.live)

        print()
        if not _criticals and not _warnings:
            print(f"RESULT: PASS — {vertical} is clear to post.\n")
        elif not _criticals:
            print(f"RESULT: PASS WITH WARNINGS — {len(_warnings)} warning(s). {vertical} can post; review above.\n")
        else:
            print(f"RESULT: FAIL — {len(_criticals)} CRITICAL issue(s). Do NOT post {vertical} until resolved.\n")
            any_critical = True

    sys.exit(1 if any_critical else 0)


if __name__ == "__main__":
    main()
