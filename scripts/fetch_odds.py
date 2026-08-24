#!/usr/bin/env python3
"""
fetch_odds.py — Live WC match moneylines from The Odds API (free tier).

Usage:
    from fetch_odds import fetch_wc_odds
    odds = fetch_wc_odds()  # returns [] if key not set or API fails

Requires:
    ODDS_API_KEY env var (register free at the-odds-api.com — 500 req/month)

Returns per match:
    {home, away, ml_home, ml_away, total, total_line, source, timestamp_utc}
    home/away are ESPN 3-letter abbreviations (e.g. "ARG", "FRA").
    ml_home/ml_away are American-format integers (e.g. -175, 220).
    total is the O/U point (float) or None. total_line is "2.5" or None.

Fallback:
    Returns [] on any error, missing key, or no events. Card renders without odds.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

SPORT_KEY = "soccer_fifa_world_cup"
API_BASE  = "https://api.the-odds-api.com/v4"

# ESPN 3-letter abbreviation lookup (full name → abbr)
# Covers all 48 WC 2026 qualified nations + common alternates
_NAME_TO_ABBR: dict[str, str] = {
    # Americas (16 teams)
    "United States":           "USA",
    "Mexico":                  "MEX",
    "Canada":                  "CAN",
    "Brazil":                  "BRA",
    "Argentina":               "ARG",
    "Uruguay":                 "URU",
    "Colombia":                "COL",
    "Ecuador":                 "ECU",
    "Venezuela":               "VEN",
    "Peru":                    "PER",
    "Chile":                   "CHI",
    "Bolivia":                 "BOL",
    "Paraguay":                "PAR",
    "Panama":                  "PAN",
    "Costa Rica":              "CRC",
    "Honduras":                "HON",
    "Jamaica":                 "JAM",
    "Guatemala":               "GUA",
    "El Salvador":             "SLV",
    "Trinidad and Tobago":     "TRI",
    # Europe (16 teams)
    "France":                  "FRA",
    "England":                 "ENG",
    "Germany":                 "GER",
    "Spain":                   "ESP",
    "Portugal":                "POR",
    "Netherlands":             "NED",
    "Belgium":                 "BEL",
    "Italy":                   "ITA",
    "Croatia":                 "CRO",
    "Switzerland":             "SUI",
    "Denmark":                 "DEN",
    "Poland":                  "POL",
    "Serbia":                  "SRB",
    "Ukraine":                 "UKR",
    "Austria":                 "AUT",
    "Czech Republic":          "CZE",
    "Slovakia":                "SVK",
    "Hungary":                 "HUN",
    "Turkey":                  "TUR",
    "Greece":                  "GRE",
    "Romania":                 "ROU",
    "Scotland":                "SCO",
    "Wales":                   "WAL",
    "Ireland":                 "IRL",
    "Norway":                  "NOR",
    "Sweden":                  "SWE",
    "Albania":                 "ALB",
    "Slovenia":                "SVN",
    "Georgia":                 "GEO",
    # Africa (9 teams)
    "Morocco":                 "MAR",
    "Senegal":                 "SEN",
    "Ghana":                   "GHA",
    "Cameroon":                "CMR",
    "Nigeria":                 "NGA",
    "Ivory Coast":             "CIV",
    "Algeria":                 "ALG",
    "Egypt":                   "EGY",
    "Tunisia":                 "TUN",
    "South Africa":            "RSA",
    "Congo DR":                "COD",
    "Angola":                  "ANG",
    "Mali":                    "MLI",
    "Burkina Faso":            "BFA",
    # Asia/Pacific (8 teams)
    "Japan":                   "JPN",
    "South Korea":             "KOR",
    "Australia":               "AUS",
    "Saudi Arabia":            "KSA",
    "Iran":                    "IRN",
    "Qatar":                   "QAT",
    "Uzbekistan":              "UZB",
    "Indonesia":               "IDN",
    "New Zealand":             "NZL",
    "New Caledonia":           "NCL",
    "Fiji":                    "FIJ",
}

# Reverse: abbr → canonical full name (for matching)
_ABBR_TO_NAME = {v: k for k, v in _NAME_TO_ABBR.items()}


def _abbr(full_name: str) -> str | None:
    """Map a full team name from The Odds API to ESPN 3-letter abbreviation."""
    name = full_name.strip()
    # Direct lookup
    if name in _NAME_TO_ABBR:
        return _NAME_TO_ABBR[name]
    # Case-insensitive
    lower = name.lower()
    for k, v in _NAME_TO_ABBR.items():
        if k.lower() == lower:
            return v
    # Partial: "United States of America" → "USA"
    for k, v in _NAME_TO_ABBR.items():
        if k.lower() in lower or lower in k.lower():
            return v
    return None


def _get_consensus_h2h(bookmakers: list) -> tuple[int | None, int | None]:
    """
    Extract consensus home/away moneylines from The Odds API bookmaker list.
    Prefers DraftKings, then FanDuel, then first available.
    Returns (ml_home, ml_away) as integers or (None, None).
    """
    priority = ["draftkings", "fanduel", "betmgm", "caesars", "betrivers"]
    h2h_by_book = {}
    for bm in bookmakers:
        key = bm.get("key", "")
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}
            h2h_by_book[key] = outcomes
            break

    if not h2h_by_book:
        return None, None

    # Pick best available book
    chosen = None
    for bk in priority:
        if bk in h2h_by_book:
            chosen = h2h_by_book[bk]
            break
    if chosen is None:
        chosen = next(iter(h2h_by_book.values()))

    # chosen is {team_name: price} — home is the API's home_team
    prices = list(chosen.values())
    if len(prices) < 2:
        return None, None
    # The Odds API puts home first in outcomes list
    non_draw = [p for name, p in chosen.items() if name != "Draw"]
    if len(non_draw) < 2:
        return None, None
    return int(non_draw[0]), int(non_draw[1])


def _get_total(bookmakers: list) -> float | None:
    """Extract the over/under point from the first available bookmaker."""
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "totals":
                continue
            for o in mkt.get("outcomes", []):
                if o.get("name") == "Over" and o.get("point") is not None:
                    return float(o["point"])
    return None


def fetch_wc_odds(api_key: str | None = None) -> list[dict]:
    """
    Fetch today's WC match moneylines from The Odds API.

    Returns list of dicts:
        {home, away, ml_home, ml_away, total, timestamp_utc}
    where home/away are ESPN 3-letter abbreviations.

    Returns [] on any error, missing key, or no markets.
    """
    key = api_key or os.environ.get("ODDS_API_KEY", "")
    if not key:
        return []

    url = (
        f"{API_BASE}/sports/{SPORT_KEY}/odds/"
        f"?apiKey={key}&regions=us&markets=h2h,totals"
        f"&oddsFormat=american&dateFormat=iso"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MarketDataBot/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            events = json.loads(r.read().decode())
    except Exception:
        return []

    if not isinstance(events, list):
        return []

    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    results = []

    for ev in events:
        home_full = ev.get("home_team", "")
        away_full = ev.get("away_team", "")
        home_abbr = _abbr(home_full)
        away_abbr = _abbr(away_full)
        if not home_abbr or not away_abbr:
            continue

        bookmakers = ev.get("bookmakers", [])
        ml_home, ml_away = _get_consensus_h2h(bookmakers)
        total = _get_total(bookmakers)

        if ml_home is None:
            continue

        results.append({
            "home":          home_abbr,
            "away":          away_abbr,
            "ml_home":       ml_home,
            "ml_away":       ml_away,
            "total":         total,
            "source":        "The Odds API",
            "timestamp_utc": timestamp_utc,
        })

    return results


def inject_odds_into_matches(matches: list[dict], odds: list[dict]) -> list[dict]:
    """
    Merge odds into ESPN match dicts in-place (pre-game matches only).
    Matches are already filtered by ESPN — only inject for state == 'pre'.
    Matching is by {home, away} abbreviation pairs.
    Returns the same list with ml_home/ml_away/total fields added where found.
    """
    if not odds:
        return matches

    odds_index = {(o["home"], o["away"]): o for o in odds}

    for m in matches:
        if m.get("state") != "pre":
            continue
        key = (m.get("home", ""), m.get("away", ""))
        if key in odds_index:
            o = odds_index[key]
            m["ml_home"]       = o["ml_home"]
            m["ml_away"]       = o["ml_away"]
            m["total"]         = o.get("total")
            m["odds_source"]   = o["source"]
            m["odds_ts"]       = o["timestamp_utc"]

    return matches
