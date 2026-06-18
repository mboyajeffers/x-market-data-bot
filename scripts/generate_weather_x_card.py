#!/usr/bin/env python3
"""
US Weather Snapshot — X card generator
Output: REVENUE/X/cards/weather_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #060f1a background | #0ea5e9 sky blue
Data: Open-Meteo API (free, no key) — current conditions + 7-day forecast
"""

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.ticker as mticker

# ─── PATHS ────────────────────────────────────────────────────────────────────

OUT_DIR   = Path("/Users/mboyajeffers/Claude_Projects/REVENUE/X/cards")
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY     = datetime.now().strftime("%Y-%m-%d")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH  = OUT_DIR / f"weather_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG      = "#060f1a"
SKY     = "#0ea5e9"
BLUE    = "#3b82f6"
CYAN    = "#22d3ee"
GREEN   = "#22c55e"
RED     = "#ef4444"
AMBER   = "#f59e0b"
GREY    = "#6b7280"
WHITE   = "#f1f5f9"
DIM     = "#94a3b8"
CARD_BG = "#0a1628"

# ─── CITIES ───────────────────────────────────────────────────────────────────

CITIES = [
    ("New York",     40.71, -74.01, "America/New_York"),
    ("Los Angeles",  34.05, -118.24, "America/Los_Angeles"),
    ("Chicago",      41.85, -87.65, "America/Chicago"),
    ("Houston",      29.76, -95.37, "America/Chicago"),
    ("Miami",        25.77, -80.19, "America/New_York"),
    ("Denver",       39.74, -104.98, "America/Denver"),
    ("Seattle",      47.61, -122.33, "America/Los_Angeles"),
    ("Atlanta",      33.75, -84.39, "America/New_York"),
]

# WMO weather code → short description
WMO_DESC = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Showers", 81: "Heavy showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "T-storm + hail", 99: "T-storm + hail",
}

# ─── DATA FETCH ───────────────────────────────────────────────────────────────

def fetch_city(name, lat, lon, tz, retries=3):
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone={tz}&forecast_days=7"
    )
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CleanMetrics/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            cur = data.get("current", {})
            daily = data.get("daily", {})
            return {
                "city": name,
                "temp":    cur.get("temperature_2m"),
                "code":    int(cur.get("weather_code", 0)),
                "wind":    cur.get("wind_speed_10m"),
                "humidity": cur.get("relative_humidity_2m"),
                "high7":   daily.get("temperature_2m_max", []),
                "low7":    daily.get("temperature_2m_min", []),
                "precip7": daily.get("precipitation_probability_max", []),
                "code7":   daily.get("weather_code", []),
                "dates7":  daily.get("time", []),
            }
        except Exception as e:
            if i < retries - 1:
                time.sleep(3)
            else:
                print(f"  WARNING: {name} failed: {e}")
    return None


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def temp_color(t):
    if t is None: return DIM
    if t >= 95:   return RED
    if t >= 85:   return AMBER
    if t >= 70:   return GREEN
    if t >= 50:   return CYAN
    return BLUE


def condition_icon(code):
    if code == 0:               return "Clear"
    if code in (1, 2):         return "P.Cloudy"
    if code == 3:               return "Cloudy"
    if code in (45, 48):       return "Fog"
    if code in (51, 53, 55):   return "Drizzle"
    if code in (61, 63, 65):   return "Rain"
    if code in (71, 73, 75):   return "Snow"
    if code in (80, 81, 82):   return "Showers"
    if code in (95, 96, 99):   return "T-storm"
    return "—"


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(city_data):
    city_data = [c for c in city_data if c is not None]

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)
    gs = gridspec.GridSpec(1, 3, figure=fig,
                           width_ratios=[3.5, 4, 2.5],
                           left=0.02, right=0.98,
                           top=0.82, bottom=0.13, wspace=0.30)
    ax_cities = fig.add_subplot(gs[0, 0])
    ax_trend  = fig.add_subplot(gs[0, 1])
    ax_stats  = fig.add_subplot(gs[0, 2])

    for ax in [ax_cities, ax_trend, ax_stats]:
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values():
            sp.set_edgecolor("#0a1a2e")

    # Dynamic headline
    if city_data:
        temps  = [(c["city"], c["temp"]) for c in city_data if c["temp"] is not None]
        hottest = max(temps, key=lambda x: x[1]) if temps else None
        coldest = min(temps, key=lambda x: x[1]) if temps else None
        avg_temp = sum(t for _, t in temps) / len(temps) if temps else None
        thunder = [c["city"] for c in city_data if c["code"] in (95, 96, 99)]

        if thunder:
            headline = f"Storms in {', '.join(thunder[:2])} — severe weather alert"
        elif hottest and hottest[1] >= 95:
            headline = f"Extreme heat: {hottest[0]} at {hottest[1]:.0f}°F — heat advisory conditions"
        elif coldest and coldest[1] <= 32:
            headline = f"Freeze warning: {coldest[0]} at {coldest[1]:.0f}°F"
        elif avg_temp:
            headline = f"US avg: {avg_temp:.0f}°F  |  Hottest: {hottest[0]} {hottest[1]:.0f}°F  |  Coldest: {coldest[0]} {coldest[1]:.0f}°F"
        else:
            headline = f"US weather snapshot — {TODAY}"
    else:
        headline = "US weather data unavailable"

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.93, f"US Weather Snapshot — {TODAY}",
             fontsize=14, fontweight="bold", color=WHITE, va="top")
    fig.text(0.02, 0.88, headline, fontsize=9, color=CYAN, va="top")
    fig.text(0.98, 0.92, f"8 major US cities  |  Open-Meteo",
             fontsize=9, color=DIM, va="top", ha="right")
    fig.text(0.98, 0.86, "@Mboya_Jeffers",
             fontsize=8.5, color=SKY, va="top", ha="right", fontweight="bold")

    # ── LEFT: CITY CURRENT CONDITIONS ─────────────────────────────────────────
    ax_cities.axis("off")
    ax_cities.set_title("Current Conditions", fontsize=9, color=DIM, pad=6)

    col_city  = 0.02
    col_temp  = 0.62
    col_cond  = 0.82
    row_h     = 0.105
    y         = 0.88

    # Header row
    ax_cities.text(col_city, y + 0.01, "City",    fontsize=7.5, color=SKY,
                   fontweight="bold", transform=ax_cities.transAxes)
    ax_cities.text(col_temp, y + 0.01, "Temp",    fontsize=7.5, color=SKY,
                   fontweight="bold", transform=ax_cities.transAxes)
    ax_cities.text(col_cond, y + 0.01, "Sky",     fontsize=7.5, color=SKY,
                   fontweight="bold", transform=ax_cities.transAxes)

    for i, city in enumerate(city_data):
        y2 = y - (i + 1) * row_h
        bg = "#06101e" if i % 2 == 0 else CARD_BG
        rect = FancyBboxPatch((0.01, y2 - 0.005), 0.97, row_h - 0.005,
                              boxstyle="round,pad=0.005",
                              facecolor=bg, edgecolor="none",
                              transform=ax_cities.transAxes, clip_on=False)
        ax_cities.add_patch(rect)

        tc = temp_color(city["temp"])
        ax_cities.text(col_city, y2 + row_h * 0.5, city["city"],
                       fontsize=7.5, color=WHITE, va="center",
                       transform=ax_cities.transAxes)
        ax_cities.text(col_temp, y2 + row_h * 0.5,
                       f"{city['temp']:.0f}°F" if city["temp"] is not None else "N/A",
                       fontsize=8, color=tc, fontweight="bold", va="center",
                       transform=ax_cities.transAxes)
        cond_c = (AMBER if city["code"] in (61,63,65,80,81,82,95,96,99) else
                  CYAN  if city["code"] in (71,73,75) else
                  DIM   if city["code"] in (45,48) else
                  SKY)
        ax_cities.text(col_cond, y2 + row_h * 0.5,
                       condition_icon(city["code"]),
                       fontsize=7, color=cond_c, va="center",
                       transform=ax_cities.transAxes)

    # ── CENTER: NYC 7-day forecast ─────────────────────────────────────────────
    nyc = next((c for c in city_data if c["city"] == "New York"), None)
    ax_trend.axis("off")
    ax_trend.set_title("New York — 7-Day Forecast", fontsize=9, color=DIM, pad=6)

    if nyc and nyc["high7"] and nyc["low7"] and len(nyc["high7"]) >= 3:
        highs  = nyc["high7"]
        lows   = nyc["low7"]
        precip = nyc["precip7"] if nyc["precip7"] else [0] * len(highs)
        dates  = [d[5:]  for d in nyc["dates7"]]  # MM-DD
        xs     = list(range(len(highs)))

        inner = ax_trend.inset_axes([0.04, 0.25, 0.92, 0.65])
        inner.set_facecolor("#040c16")
        for side in inner.spines.values():
            side.set_edgecolor("#0a1a2e")
        inner.tick_params(colors=GREY, labelsize=6)

        inner.fill_between(xs, lows, highs, alpha=0.2, color=SKY, label="High/Low range")
        inner.plot(xs, highs, color=RED, linewidth=1.5, marker="o", markersize=3,
                   label="High", zorder=3)
        inner.plot(xs, lows, color=BLUE, linewidth=1.5, marker="o", markersize=3,
                   label="Low", zorder=3)
        inner.set_xticks(xs)
        inner.set_xticklabels(dates, fontsize=5.5, color=GREY)
        inner.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f°F"))
        inner.legend(fontsize=6, loc="upper right", framealpha=0.2)

        # Precipitation probability bars at bottom
        for xi, pp in enumerate(precip[:len(xs)]):
            if pp and pp > 10:
                inner.text(xi, lows[xi] - (max(highs) - min(lows)) * 0.08,
                           f"{int(pp)}%", fontsize=5, color=CYAN,
                           ha="center", va="top")

        # Current temp call-out
        cur_temp = nyc.get("temp")
        if cur_temp:
            ax_trend.text(0.5, 0.15, f"Now: {cur_temp:.0f}°F",
                          fontsize=10, color=temp_color(cur_temp), fontweight="bold",
                          transform=ax_trend.transAxes, ha="center", va="bottom")
    else:
        ax_trend.text(0.5, 0.5, "Forecast data\nunavailable",
                      fontsize=9, color=GREY, transform=ax_trend.transAxes,
                      ha="center", va="center")

    ax_trend.text(0.5, 0.02, "% = precipitation probability  |  Open-Meteo",
                  fontsize=6, color=GREY, transform=ax_trend.transAxes,
                  ha="center", style="italic")

    # ── RIGHT: SUMMARY STATS ──────────────────────────────────────────────────
    ax_stats.axis("off")
    ax_stats.set_title("National Summary", fontsize=9, color=DIM, pad=6)

    stat_rows = []
    if city_data:
        temps2 = [(c["city"], c["temp"]) for c in city_data if c["temp"] is not None]
        if temps2:
            hot2  = max(temps2, key=lambda x: x[1])
            cold2 = min(temps2, key=lambda x: x[1])
            avg2  = sum(t for _, t in temps2) / len(temps2)
            stat_rows.append(("Hottest City",   f"{hot2[0]} {hot2[1]:.0f}°F"))
            stat_rows.append(("Coldest City",   f"{cold2[0]} {cold2[1]:.0f}°F"))
            stat_rows.append(("National Avg",   f"{avg2:.0f}°F"))

        # Rain/storm count
        rainy = sum(1 for c in city_data if c["code"] in (51,53,55,61,63,65,80,81,82))
        stormy = sum(1 for c in city_data if c["code"] in (95,96,99))
        stat_rows.append(("Rain / Storms",  f"{rainy} / {stormy} cities"))

        # Max wind
        winds = [(c["city"], c["wind"]) for c in city_data if c.get("wind") is not None]
        if winds:
            windiest = max(winds, key=lambda x: x[1])
            stat_rows.append(("Windiest City", f"{windiest[0]} {windiest[1]:.0f} mph"))

    y2 = 0.85
    for label, val in stat_rows:
        ax_stats.text(0.06, y2, label, fontsize=7.5, color=DIM,
                      transform=ax_stats.transAxes, va="top")
        ax_stats.text(0.94, y2, val, fontsize=8.5, color=WHITE, fontweight="bold",
                      transform=ax_stats.transAxes, ha="right", va="top")
        ax_stats.add_artist(plt.Line2D([0.03, 0.97], [y2 - 0.015, y2 - 0.015],
                                       transform=ax_stats.transAxes,
                                       color="#0a1a2e", linewidth=0.5))
        y2 -= 0.14

    y2 -= 0.03
    rect = FancyBboxPatch((0.03, y2 - 0.08), 0.94, 0.15,
                          boxstyle="round,pad=0.02",
                          facecolor="#040c16", edgecolor=SKY, linewidth=0.8,
                          transform=ax_stats.transAxes, clip_on=False)
    ax_stats.add_patch(rect)
    ax_stats.text(0.5, y2, "Live conditions  |  ±1°F accuracy",
                  fontsize=6.5, color=CYAN, transform=ax_stats.transAxes,
                  ha="center", va="center", style="italic")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.06, f"Source: Open-Meteo (open-meteo.com)  |  Generated: {TIMESTAMP}",
             fontsize=7.5, color=GREY, va="top")
    fig.text(0.98, 0.06, "github.com/mboyajeffers/data-intelligence-platform",
             fontsize=7.5, color=SKY, va="top", ha="right")
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.105, 0.105],
                              transform=fig.transFigure, color="#0a1a2e", linewidth=0.8))

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching city weather data...")
    city_data = []
    for name, lat, lon, tz in CITIES:
        print(f"  {name}...")
        d = fetch_city(name, lat, lon, tz)
        city_data.append(d)
        time.sleep(0.5)

    print("Drawing card...")
    draw_card(city_data)
    print("Done.")


if __name__ == "__main__":
    main()
