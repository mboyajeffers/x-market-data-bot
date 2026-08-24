#!/usr/bin/env python3
"""
Preview orchestrator for the X bot — @Mboya_Jeffers.

For each requested vertical: generate the card (live data), build the caption,
run all verification layers, and freeze the result into staging.json. Nothing
is posted here. The xbot CLI reads staging.json to post approved items.

The staging record is self-contained (card path + caption + verification +
state) so the same file can later drive a separate preview/approve UI.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BOT_DIR))

from post import VERTICALS, CAPTION_BUILDERS, TEXT_ONLY_VERTICALS, run_generator
import verify

STAGING_PATH = BOT_DIR / "staging.json"
ALL_VERTICALS = list(VERTICALS.keys())


def load_staging():
    if not STAGING_PATH.exists():
        return {"posts": []}
    try:
        return json.loads(STAGING_PATH.read_text())
    except Exception:
        return {"posts": []}


def save_staging(data):
    STAGING_PATH.write_text(json.dumps(data, indent=2))


def _upsert(data, entry):
    """Replace any existing staged entry for the same vertical, else append."""
    data["posts"] = [p for p in data["posts"] if p["vertical"] != entry["vertical"]]
    data["posts"].append(entry)


def preview_one(vertical):
    """Generate + caption + verify a single vertical. Returns the staging entry."""
    print(f"\n=== {vertical} ===")
    is_text_only = vertical in TEXT_ONLY_VERTICALS
    entry = {
        "vertical":        vertical,
        "post_type":       "text" if is_text_only else "card",
        "card_path":       None,
        "caption":         None,
        "char_count":      0,
        "verification":    {"status": verify.FAIL, "checks": []},
        "preview_time":    datetime.now().isoformat(timespec="seconds"),
        "approved":        False,
        "posted":          False,
        "posted_tweet_id": None,
    }

    if not is_text_only:
        try:
            card_path = run_generator(vertical)
            entry["card_path"] = str(card_path)
        except Exception as e:
            entry["verification"] = {"status": verify.FAIL,
                                     "checks": [{"layer": "card", "name": "generator",
                                                 "status": verify.FAIL, "detail": str(e)[:200]}]}
            print(f"  GENERATOR FAILED: {e}")
            return entry

    card_path = entry["card_path"]  # None for text-only

    try:
        caption = CAPTION_BUILDERS[vertical]()
        entry["caption"] = caption
        entry["char_count"] = len(caption)
    except Exception as e:
        entry["verification"] = {"status": verify.FAIL,
                                 "checks": [{"layer": "caption", "name": "builder",
                                             "status": verify.FAIL, "detail": str(e)[:200]}]}
        print(f"  CAPTION FAILED: {e}")
        return entry

    entry["verification"] = verify.verify_all(
        vertical, caption, card_path, post_type=entry["post_type"]
    )
    print(verify.format_report(vertical, entry["verification"]))
    return entry


def preview(verticals=None):
    """Preview a list of verticals (default: all). Writes staging.json."""
    verticals = verticals or ALL_VERTICALS
    data = load_staging()

    for i, v in enumerate(verticals):
        if v not in VERTICALS:
            print(f"Unknown vertical: {v} — skipping")
            continue
        entry = preview_one(v)
        _upsert(data, entry)
        save_staging(data)  # incremental — survives a mid-run crash
        if i < len(verticals) - 1:
            time.sleep(1)  # gentle pacing between API-heavy generators

    print_summary(data, verticals)
    return data


def print_summary(data, verticals=None):
    """Terminal summary table of staged posts."""
    rows = [p for p in data["posts"]
            if verticals is None or p["vertical"] in verticals]
    rows.sort(key=lambda p: p["vertical"])

    icon = {verify.PASS: "✓ PASS", verify.WARN: "▲ WARN", verify.FAIL: "✗ FAIL"}
    print("\n" + "=" * 60)
    print(f"{'VERTICAL':<12} {'STATUS':<8} {'CHARS':<7} {'POSTED'}")
    print("-" * 60)
    for p in rows:
        st = p["verification"]["status"]
        posted = "yes" if p["posted"] else "—"
        print(f"{p['vertical']:<12} {icon.get(st, st):<8} {p['char_count']:<7} {posted}")
    print("=" * 60)
    postable = [p["vertical"] for p in rows
                if p["verification"]["status"] in (verify.PASS, verify.WARN) and not p["posted"]]
    blocked = [p["vertical"] for p in rows if p["verification"]["status"] == verify.FAIL]
    if postable:
        print(f"Ready to post ({len(postable)}): {', '.join(postable)}")
    if blocked:
        print(f"BLOCKED ({len(blocked)}): {', '.join(blocked)} — fix and re-preview")
    print("Approve with:  xbot post all   |   xbot post <vertical>")


if __name__ == "__main__":
    args = sys.argv[1:]
    preview(args if args else None)
