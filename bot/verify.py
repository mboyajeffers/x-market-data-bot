#!/usr/bin/env python3
"""
Verification module for the X bot — @Mboya_Jeffers.

Three layers of pre-post scrutiny so nothing inaccurate, malformed, or
off-brand reaches the timeline:

  verify_caption(vertical, caption)  — X rules + FTC + completeness
  verify_card(vertical, card_path)   — render quality + freshness + branding
  verify_data(vertical, caption)     — data authenticity heuristics

Each check returns a (name, status, detail) tuple where status is one of
PASS / WARN / FAIL. verify_all() aggregates: FAIL if any check fails, WARN
if any warns, else PASS. Only PASS/WARN verticals are postable.

Catches the June 25 class of failure (two cashtags → 403) before posting.
"""

import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BOT_DIR     = Path(__file__).parent.resolve()
SCRIPTS_DIR = BOT_DIR.parent / "scripts"

sys.path.insert(0, str(BOT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from affiliate_config import REQUIRES_DISCLOSURE, VERTICAL_CASHTAGS, BIO_LINK

try:
    from vertical_colors import VERTICAL as VERTICAL_COLORS
except Exception:
    VERTICAL_COLORS = {}

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_RANK = {PASS: 0, WARN: 1, FAIL: 2}

CASHTAG_RE     = re.compile(r"\$[A-Z]{1,6}\b")
PLACEHOLDER_RE = re.compile(r"\[[A-Z0-9_]+\]")

# Known no-data fallback signatures — when a caption builder's live fetch fails
# it emits one of these instead of real numbers. Posting one is a silent lie.
FALLBACK_SIGNATURES = [
    "Live S&P 500 sector data.",          # build_caption_finance fallback
]

# AI-sounding filler phrases — flagged as WARN on insight (text-only) posts
AI_FILLER_PHRASES = [
    "it's worth noting", "worth noting", "interestingly", "dive into",
    "let that sink in", "game-changing", "buckle up", "it's important",
    "at the end of the day", "in conclusion", "as of today", "navigate",
    "i think", "in my opinion", "that said,", "importantly,",
]


# ─── CAPTION ──────────────────────────────────────────────────────────────────

def verify_caption(vertical, caption, post_type="card"):
    checks = []

    n = len(caption)
    checks.append(("char_count", FAIL if n > 280 else PASS, f"{n}/280 chars"))

    cashtags = CASHTAG_RE.findall(caption)
    if len(cashtags) > 1:
        checks.append(("cashtag_limit", FAIL,
                       f"{len(cashtags)} cashtags ({', '.join(cashtags)}) — X allows 1"))
    else:
        checks.append(("cashtag_limit", PASS,
                       f"{len(cashtags)} cashtag" + (f" ({cashtags[0]})" if cashtags else "")))

    placeholders = sorted(set(PLACEHOLDER_RE.findall(caption)))
    if placeholders:
        checks.append(("no_placeholders", FAIL,
                       f"unfilled: {', '.join(placeholders)}"))
    else:
        checks.append(("no_placeholders", PASS, "none"))

    if vertical in REQUIRES_DISCLOSURE:
        has_ad = "#ad" in caption.lower()
        checks.append(("ftc_disclosure", PASS if has_ad else FAIL,
                       "#ad present" if has_ad else "#ad MISSING (FTC required)"))

    has_source = any(s in caption for s in
                     ("Source:", "Not investment advice", "Not legal", "Not tax",
                      "Not betting advice"))
    checks.append(("source_attribution", PASS if has_source else WARN,
                   "present" if has_source else "no source / disclaimer line"))

    has_cta = (BIO_LINK in caption) or ("→" in caption) or ("contra.com" in caption)
    checks.append(("cta_present", PASS if has_cta else WARN,
                   "present" if has_cta else "no CTA / bio link"))

    # For text-only insight posts: check for AI filler phrases
    if post_type == "text":
        lower = caption.lower()
        found = [p for p in AI_FILLER_PHRASES if p in lower]
        if found:
            checks.append(("no_ai_phrases", WARN,
                           f"AI-sounding phrases detected: {', '.join(found[:3])}"))
        else:
            checks.append(("no_ai_phrases", PASS, "no filler phrases detected"))

    return checks


# ─── CARD ─────────────────────────────────────────────────────────────────────

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _color_present(img, target_rgb, tol=40, samples=60):
    """True if any sampled pixel is within tol (per-channel) of target_rgb."""
    w, h = img.size
    tr, tg, tb = target_rgb
    for i in range(samples):
        x = int(w * (i + 0.5) / samples)
        for j in range(samples):
            y = int(h * (j + 0.5) / samples)
            r, g, b = img.getpixel((x, y))[:3]
            if abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol:
                return True
    return False


def verify_card(vertical, card_path):
    checks = []
    p = Path(card_path)

    if not p.exists():
        return [("card_exists", FAIL, f"not found: {card_path}")]

    # Freshness — a stale card means the generator silently failed and an old
    # PNG would be reused. Must be regenerated today.
    mtime = datetime.fromtimestamp(p.stat().st_mtime).date()
    today = datetime.now().date()
    checks.append(("card_fresh", PASS if mtime == today else FAIL,
                   f"generated {mtime}" + ("" if mtime == today else " (STALE)")))

    size = p.stat().st_size
    checks.append(("card_filesize", PASS if 50_000 < size < 8_000_000 else FAIL,
                   f"{size // 1024} KB"))

    try:
        from PIL import Image
        img = Image.open(p).convert("RGB")
    except Exception as e:
        checks.append(("card_readable", FAIL, f"cannot open: {e}"))
        return checks

    w, h = img.size
    landscape_ok = w >= 1000 and h >= 500 and w > h
    checks.append(("card_dimensions", PASS if landscape_ok else FAIL,
                   f"{w}x{h}" + ("" if landscape_ok else " (not landscape/too small)")))

    cx, cy = w // 2, h // 2
    not_blank = img.getpixel((cx, cy)) != (255, 255, 255)
    checks.append(("card_not_blank", PASS if not_blank else FAIL,
                   "rendered" if not_blank else "center is white (blank render)"))

    accent = VERTICAL_COLORS.get(vertical, {}).get("accent")
    if accent:
        present = _color_present(img, _hex_to_rgb(accent))
        checks.append(("brand_color", PASS if present else WARN,
                       f"accent {accent} " + ("present" if present else "not detected")))

    return checks


# ─── DATA AUTHENTICITY ────────────────────────────────────────────────────────

def _fetch_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _crypto_cross_source():
    """Compare CoinGecko BTC price vs Binance mark. Strongest authenticity signal."""
    try:
        cg = _fetch_json("https://api.coingecko.com/api/v3/simple/price"
                         "?ids=bitcoin&vs_currencies=usd")
        cg_btc = float(cg["bitcoin"]["usd"])
    except Exception as e:
        return ("crypto_cross_source", WARN, f"CoinGecko price unavailable ({e})")
    try:
        bn = _fetch_json("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
        bn_btc = float(bn["markPrice"])
    except Exception as e:
        return ("crypto_cross_source", WARN, f"Binance price unavailable ({e})")

    diff_pct = abs(cg_btc - bn_btc) / cg_btc * 100
    if diff_pct <= 2.0:
        return ("crypto_cross_source", PASS,
                f"CoinGecko ${cg_btc:,.0f} vs Binance ${bn_btc:,.0f} ({diff_pct:.2f}% apart)")
    return ("crypto_cross_source", WARN,
            f"sources diverge {diff_pct:.1f}% (CG ${cg_btc:,.0f} / BN ${bn_btc:,.0f})")


def verify_data(vertical, caption):
    checks = []

    # 1. Fallback / no-data detection
    fallback_hit = next((s for s in FALLBACK_SIGNATURES if s in caption), None)
    if fallback_hit:
        checks.append(("data_fallback", FAIL,
                       "live fetch failed — caption is using a no-data fallback"))
    else:
        checks.append(("data_fallback", PASS, "no fallback signature"))

    # 2. Numeric presence — a data card with no numbers is suspect
    body = "\n".join(l for l in caption.splitlines()
                     if not l.strip().startswith(("Source:", "Not ", "#", "→"))
                     and "→" not in l)
    has_numbers = bool(re.search(r"\d", body))
    checks.append(("data_numeric", PASS if has_numbers else WARN,
                   "numeric data present" if has_numbers else "no numbers detected in body"))

    # 3. Sanity ranges parsed from caption
    vix = re.search(r"VIX:\s*([\d.]+)", caption)
    if vix:
        v = float(vix.group(1))
        ok = 5 <= v <= 90
        checks.append(("sanity_vix", PASS if ok else WARN,
                       f"VIX {v}" + ("" if ok else " out of 5-90 range")))
    dom = re.search(r"BTC dom:\s*([\d.]+)%", caption)
    if dom:
        d = float(dom.group(1))
        ok = 30 <= d <= 70
        checks.append(("sanity_btc_dom", PASS if ok else WARN,
                       f"BTC dom {d}%" + ("" if ok else " out of 30-70 range")))

    # 4. Vertical-specific authenticity
    if vertical == "crypto":
        checks.append(_crypto_cross_source())

    if vertical in ("worldcup", "betting"):
        has_match = any(k in caption for k in ("LIVE", "FT:", "Today:", "Later:",
                                               "Yest", "Yesterday", "-"))
        checks.append(("match_data", PASS if has_match else WARN,
                       "match data present" if has_match
                       else "no scores/fixtures — ESPN may have returned nothing"))

    return checks


# ─── AGGREGATE ────────────────────────────────────────────────────────────────

def verify_all(vertical, caption, card_path, post_type="card"):
    """Run all three layers. Returns {status, checks:[{layer,name,status,detail}]}.
    For text-only posts (post_type='text') card verification is skipped entirely.
    """
    all_checks = []
    layers = [
        ("caption", verify_caption(vertical, caption, post_type=post_type)),
        ("data",    verify_data(vertical, caption)),
    ]
    if post_type != "text" and card_path is not None:
        layers.insert(1, ("card", verify_card(vertical, card_path)))

    for layer, fn_checks in layers:
        for name, status, detail in fn_checks:
            all_checks.append({"layer": layer, "name": name,
                               "status": status, "detail": detail})

    overall = PASS
    for c in all_checks:
        if _RANK[c["status"]] > _RANK[overall]:
            overall = c["status"]

    return {"status": overall, "checks": all_checks}


def format_report(vertical, result):
    """Human-readable verification block for terminal output."""
    icon = {PASS: "✓", WARN: "▲", FAIL: "✗"}
    lines = [f"  [{result['status']}] verification:"]
    for c in result["checks"]:
        if c["status"] != PASS:  # show only WARN/FAIL by default
            lines.append(f"    {icon[c['status']]} {c['layer']}.{c['name']}: {c['detail']}")
    if all(c["status"] == PASS for c in result["checks"]):
        lines.append("    ✓ all checks passed")
    return "\n".join(lines)
