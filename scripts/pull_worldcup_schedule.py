#!/usr/bin/env python3
"""
FIFA World Cup 2026 — full schedule puller.

Iterates every tournament date (2026-06-11 → 2026-07-19), fetches the ESPN
scoreboard per day, and saves:
  schedule/worldcup_schedule.json   — machine-readable (drives post timing)
  schedule/WORLDCUP_SCHEDULE.md     — human table with recommended post times

Re-runnable: ESPN populates later-round fixtures as dates approach, so re-run
periodically to fill in the bracket. Recommended post time = ~75 min before the
day's earliest kickoff (mirrors the retired cron's "post before kickoffs" logic).

Usage:
    python3 pull_worldcup_schedule.py
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Reuse the proven ESPN parse + stage logic from the card generator.
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))
from generate_worldcup_x_card import _parse_scoreboard, _fetch, get_stage  # noqa: E402

OUT_DIR   = SCRIPTS_DIR.parent / "schedule"
JSON_PATH = OUT_DIR / "worldcup_schedule.json"
MD_PATH   = OUT_DIR / "WORLDCUP_SCHEDULE.md"

START = datetime(2026, 6, 11)
END   = datetime(2026, 7, 19)

POST_LEAD_MIN = 75  # minutes before earliest kickoff to post


def _kickoff_dt_et(match_time, date):
    """Parse an 'H:MMam/pm ET' string back to a naive ET datetime on `date`."""
    t = (match_time or "").replace(" ET", "").strip()
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            parsed = datetime.strptime(t, fmt)
            return date.replace(hour=parsed.hour, minute=parsed.minute,
                                second=0, microsecond=0)
        except ValueError:
            continue
    return None


def fetch_day(date):
    url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
           f"fifa.world/scoreboard?dates={date.strftime('%Y%m%d')}")
    try:
        return _parse_scoreboard(_fetch(url))
    except Exception as e:
        print(f"  {date:%Y-%m-%d}: fetch error ({e})")
        return []


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days = []
    total_matches = 0

    date = START
    while date <= END:
        matches = fetch_day(date)
        if matches:
            # Exclude TBD/placeholder kickoffs (ESPN returns 00:00 for unscheduled
            # times). No WC2026 match kicks off before ~9AM ET, so anything earlier
            # is a placeholder and must not drive the recommended post time.
            kickoffs = [k for k in (_kickoff_dt_et(m["time"], date) for m in matches)
                        if k and k.hour >= 9]
            earliest = min(kickoffs) if kickoffs else None
            post_dt  = (earliest - timedelta(minutes=POST_LEAD_MIN)) if earliest else None
            days.append({
                "date":            date.strftime("%Y-%m-%d"),
                "weekday":         date.strftime("%a"),
                "stage":           _stage_for(date),
                "match_count":     len(matches),
                "matches":         [{"home": m["home"], "away": m["away"],
                                     "time": m["time"], "is_usa": m["is_usa"]}
                                    for m in matches],
                "earliest_kickoff_et": earliest.strftime("%-I:%M%p ET") if earliest else None,
                "recommended_post_et": post_dt.strftime("%-I:%M%p ET") if post_dt else None,
            })
            total_matches += len(matches)
            print(f"  {date:%Y-%m-%d} ({date:%a}): {len(matches)} match(es)"
                  + (f" — first {earliest:%-I:%M%p} ET" if earliest else ""))
        date += timedelta(days=1)
        time.sleep(0.25)

    payload = {
        "tournament":  "FIFA World Cup 2026",
        "generated":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "window":      f"{START:%Y-%m-%d} → {END:%Y-%m-%d}",
        "days_with_matches": len(days),
        "total_matches":     total_matches,
        "post_lead_minutes": POST_LEAD_MIN,
        "days":        days,
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2))
    MD_PATH.write_text(_render_md(payload))
    print(f"\nSaved {len(days)} match days ({total_matches} matches):")
    print(f"  {JSON_PATH}")
    print(f"  {MD_PATH}")


def _stage_for(date):
    """Stage label for an arbitrary date (get_stage() reads 'now', so map by date)."""
    d = date.month * 100 + date.day
    if d <= 627: return "Group Stage"
    if d <= 704: return "Round of 32"
    if d <= 709: return "Round of 16"
    if d <= 713: return "Quarterfinals"
    if d <= 716: return "Semifinals"
    if d <= 719: return "Final / 3rd Place"
    return "Post-Tournament"


def _render_md(payload):
    lines = [
        "# FIFA World Cup 2026 — Posting Schedule",
        "",
        f"**Generated:** {payload['generated']}  ",
        f"**Window:** {payload['window']}  ",
        f"**Match days:** {payload['days_with_matches']} · "
        f"**Total matches:** {payload['total_matches']}  ",
        "",
        "> Source: ESPN. Re-run `scripts/pull_worldcup_schedule.py` to refresh — later-round",
        "> fixtures populate as dates approach. **Recommended post time = "
        f"{payload['post_lead_minutes']} min before the day's first kickoff.**",
        "",
        "| Date | Day | Stage | Matches | First KO (ET) | Post by (ET) |",
        "|------|-----|-------|---------|---------------|--------------|",
    ]
    for d in payload["days"]:
        sample = " · ".join(
            f"{'🇺🇸 ' if m['is_usa'] else ''}{m['home']}-{m['away']}"
            for m in d["matches"][:4]
        )
        if d["match_count"] > 4:
            sample += f" +{d['match_count'] - 4} more"
        lines.append(
            f"| {d['date']} | {d['weekday']} | {d['stage']} | {sample} | "
            f"{d['earliest_kickoff_et'] or '—'} | "
            f"**{d['recommended_post_et'] or '—'}** |"
        )
    lines.append("")
    lines.append("## How to use")
    lines.append("")
    lines.append("On a match day, around the **Post by** time:")
    lines.append("```")
    lines.append("source ~/.x_bot_env && ~/Claude_Projects/REVENUE/X/bot/xbot preview worldcup betting")
    lines.append("# review inline, then:")
    lines.append("~/Claude_Projects/REVENUE/X/bot/xbot post worldcup")
    lines.append("```")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    build()
