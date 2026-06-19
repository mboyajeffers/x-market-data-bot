#!/usr/bin/env python3
"""
SEC Compliance Tracker — X card generator
Output: REVENUE/X/cards/compliance_x_card_YYYY-MM-DD.png (1200x675px)
Theme: #08082a background | #4f46e5 indigo | white text
Data: SEC EDGAR full-text search API (free, no key) + EDGAR company search
"""

import json
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch

# ─── PATHS ────────────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent.parent / "cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY = datetime.now().strftime("%Y-%m-%d")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH = OUT_DIR / f"compliance_x_card_{TODAY}.png"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG      = "#08082a"
INDIGO  = "#4f46e5"
PURPLE  = "#7c3aed"
GREEN   = "#22c55e"
RED     = "#ef4444"
AMBER   = "#f59e0b"
GREY    = "#6b7280"
WHITE   = "#f1f5f9"
DIM     = "#94a3b8"
CARD_BG = "#0f0f38"

# ─── EDGAR API ────────────────────────────────────────────────────────────────

EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FULL = "https://efts.sec.gov/LATEST/search-index?q=%22administrative+proceeding%22&dateRange=custom&startdt={start}&enddt={end}&forms=33-8,34-8,IC-4"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={query}&forms={forms}&dateRange=custom&startdt={start}&enddt={end}"

HEADERS = {
    "User-Agent": "CleanMetrics data-pipeline contact@cleanmetrics.io",
    "Accept": "application/json",
}


def edgar_search(query, forms, start_date, end_date, max_retries=3):
    """Search EDGAR EFTS full-text search."""
    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q={urllib.parse.quote(query)}"
        f"&forms={forms}"
        f"&dateRange=custom&startdt={start_date}&enddt={end_date}"
        f"&_source=period_of_report,entity_name,file_date,form_type,period_of_report"
    )
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep((attempt + 1) * 15)
                continue
            print(f"  WARNING: EDGAR HTTP {e.code} — query={query[:30]}")
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(8)
                continue
            print(f"  WARNING: EDGAR search failed: {e}")
            return None


def edgar_company_search(form_type, start_date, end_date, max_retries=3):
    """Get recent filings of a specific form type via EDGAR submissions."""
    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?forms={form_type}"
        f"&dateRange=custom&startdt={start_date}&enddt={end_date}"
    )
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return None


# Add missing import
import urllib.parse


def fetch_enforcement_data():
    """
    Fetch SEC enforcement proxy data from EDGAR:
    - 8-K filings mentioning "SEC investigation" or "enforcement" (30d)
    - Form 33-8 / 34-8 admin proceedings
    - Count by industry category (SIC-based approximation)
    """
    end = datetime.now()
    start_30d = (end - timedelta(days=30)).strftime("%Y-%m-%d")
    start_7d  = (end - timedelta(days=7)).strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    results = {}

    # 1. 8-K filings mentioning SEC investigation (30d)
    print("  Querying 8-K SEC investigation mentions (30d)...")
    data_8k = edgar_search(
        '"SEC investigation" OR "securities investigation"',
        "8-K",
        start_30d, end_str
    )
    results["8k_investigation_30d"] = data_8k.get("hits", {}).get("total", {}).get("value", 0) if data_8k else 0

    # 2. 8-K enforcement/subpoena mentions (30d)
    print("  Querying 8-K enforcement/subpoena mentions (30d)...")
    data_sub = edgar_search(
        '"subpoena" OR "grand jury" OR "DOJ investigation"',
        "8-K",
        start_30d, end_str
    )
    results["8k_subpoena_30d"] = data_sub.get("hits", {}).get("total", {}).get("value", 0) if data_sub else 0

    # 3. S-1 registration (IPO pipeline, 30d)
    print("  Querying S-1 registrations (30d)...")
    data_s1 = edgar_company_search("S-1", start_30d, end_str)
    results["s1_filings_30d"] = data_s1.get("hits", {}).get("total", {}).get("value", 0) if data_s1 else 0

    # 4. Recent enforcement (7d)
    print("  Querying 8-K SEC enforcement (7d)...")
    data_7d = edgar_search('"SEC" "enforcement" OR "penalty" OR "fine"', "8-K", start_7d, end_str)
    results["8k_enforcement_7d"] = data_7d.get("hits", {}).get("total", {}).get("value", 0) if data_7d else 0

    # 5. Annual reports (10-K, 30d) — proxy for corporate activity
    print("  Querying 10-K filings (30d)...")
    data_10k = edgar_company_search("10-K", start_30d, end_str)
    results["10k_filings_30d"] = data_10k.get("hits", {}).get("total", {}).get("value", 0) if data_10k else 0

    # 6. Recent 8-K count (total activity, 7d) — market baseline
    print("  Querying total 8-K filings (7d)...")
    data_all8k = edgar_company_search("8-K", start_7d, end_str)
    results["8k_total_7d"] = data_all8k.get("hits", {}).get("total", {}).get("value", 0) if data_all8k else 0

    return results, start_30d, end_str


def fetch_notable_enforcement(start_date, end_date):
    """Get recent filing snippets for the enforcement table."""
    data = edgar_search('"SEC investigation"', "8-K", start_date, end_date)
    if not data:
        return []
    hits = data.get("hits", {}).get("hits", [])
    filings = []
    for h in hits[:5]:
        src = h.get("_source", {})
        # display_names: ["Company Name  (TICK)  (CIK 0001234567)"]
        raw_names = src.get("display_names", [])
        if raw_names:
            entity = raw_names[0].split("(")[0].strip()[:28]
        else:
            entity = "Unknown"
        filings.append({
            "entity": entity,
            "date": src.get("file_date", "")[:10],
            "form": src.get("form", "8-K"),
        })
    return filings


# ─── DRAW ─────────────────────────────────────────────────────────────────────

def draw_card(enforcement, filings, start_30d, end_str):
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(12, 6.75), dpi=300, facecolor=BG)

    gs = gridspec.GridSpec(
        1, 3,
        figure=fig,
        width_ratios=[3.5, 3.5, 3],
        left=0.02, right=0.98,
        top=0.82, bottom=0.13,
        wspace=0.32,
    )

    ax_bars  = fig.add_subplot(gs[0, 0])
    ax_table = fig.add_subplot(gs[0, 1])
    ax_stats = fig.add_subplot(gs[0, 2])

    for ax in [ax_bars, ax_table, ax_stats]:
        ax.set_facecolor(CARD_BG)
        for spine in ax.spines.values():
            spine.set_edgecolor("#1a1a4a")

    total_actions = enforcement.get("8k_investigation_30d", 0) + enforcement.get("8k_subpoena_30d", 0)
    s1_30d   = enforcement.get("s1_filings_30d", 0)
    enf_7d   = enforcement.get("8k_enforcement_7d", 0)

    # Dynamic insight headline
    if total_actions > 50:
        headline = f"Enforcement elevated: {total_actions} investigation/subpoena 8-Ks in 30 days"
    elif enf_7d > 20:
        headline = f"Active week: {enf_7d} enforcement-related 8-K filings in 7 days"
    elif s1_30d > 30:
        headline = f"IPO pipeline active: {s1_30d} S-1 registrations filed in 30 days"
    elif total_actions < 5:
        headline = f"Quiet enforcement period: {total_actions} investigation-related 8-Ks in 30 days"
    else:
        headline = f"EDGAR (30d): {total_actions} enforcement-related  |  {s1_30d} S-1 registrations"

    # ── HEADER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.93, f"SEC Enforcement Tracker — {TODAY}",
             fontsize=14, fontweight="bold", color=WHITE, va="top")
    fig.text(0.02, 0.88, headline,
             fontsize=9, color=INDIGO, va="top")
    fig.text(0.98, 0.92,
             f"Enforcement-related 8-Ks (30d): {total_actions}",
             fontsize=9, color=INDIGO, va="top", ha="right")
    fig.text(0.98, 0.86, "@Mboya_Jeffers",
             fontsize=8.5, color=INDIGO, va="top", ha="right", fontweight="bold")

    # ── LEFT: ACTIVITY BAR CHART ──────────────────────────────────────────────
    ax_bars.axis("off")
    ax_bars.set_title("EDGAR Filing Activity (30d)", fontsize=9, color=DIM, pad=6)

    categories = [
        ("10-K Annual Reports", enforcement.get("10k_filings_30d", 0), INDIGO),
        ("S-1 Registrations",   enforcement.get("s1_filings_30d", 0), PURPLE),
        ("8-K SEC Investigation", enforcement.get("8k_investigation_30d", 0), AMBER),
        ("8-K Subpoena/DOJ",    enforcement.get("8k_subpoena_30d", 0), RED),
    ]

    max_val = max(v for _, v, _ in categories) or 1
    bar_x_start = 0.02
    bar_area_w  = 0.80

    y_positions = [0.82, 0.65, 0.48, 0.31]
    bar_h = 0.10

    for i, ((label, val, color), y) in enumerate(zip(categories, y_positions)):
        bar_w = (val / max_val) * bar_area_w
        # Background track
        ax_bars.add_patch(FancyBboxPatch(
            (bar_x_start, y), bar_area_w, bar_h,
            boxstyle="round,pad=0.01",
            facecolor="#1a1a4a", edgecolor="none",
            transform=ax_bars.transAxes, clip_on=True
        ))
        # Value bar
        if bar_w > 0.005:
            ax_bars.add_patch(FancyBboxPatch(
                (bar_x_start, y), bar_w, bar_h,
                boxstyle="round,pad=0.01",
                facecolor=color, edgecolor="none", alpha=0.85,
                transform=ax_bars.transAxes, clip_on=True
            ))
        # Label above
        ax_bars.text(bar_x_start, y + bar_h + 0.025, label,
                     fontsize=7.5, color=DIM,
                     transform=ax_bars.transAxes, va="bottom")
        # Count label
        ax_bars.text(bar_x_start + bar_area_w + 0.02, y + bar_h / 2,
                     str(val), fontsize=9, color=color, fontweight="bold",
                     transform=ax_bars.transAxes, va="center")

    ax_bars.text(0.5, 0.02, f"{start_30d} to {end_str}",
                 fontsize=6, color=GREY, transform=ax_bars.transAxes,
                 ha="center", style="italic")

    # ── CENTER: RECENT FILING TABLE ────────────────────────────────────────────
    ax_table.axis("off")
    ax_table.set_title("Recent 8-K: SEC Investigation", fontsize=9, color=DIM, pad=6)

    if filings:
        col_x = [0.03, 0.70, 0.95]
        y_h = 0.88
        ax_table.text(col_x[0], y_h, "Entity", fontsize=7.5, color=INDIGO,
                      fontweight="bold", transform=ax_table.transAxes)
        ax_table.text(col_x[1], y_h, "Filed", fontsize=7.5, color=INDIGO,
                      fontweight="bold", transform=ax_table.transAxes)

        row_h = 0.14
        y = y_h - 0.06
        for i, f in enumerate(filings):
            bg = "#08082a" if i % 2 == 0 else CARD_BG
            rect = FancyBboxPatch((0.01, y - 0.01), 0.98, row_h,
                                  boxstyle="round,pad=0.01",
                                  facecolor=bg, edgecolor="none",
                                  transform=ax_table.transAxes, clip_on=False)
            ax_table.add_patch(rect)
            ax_table.text(col_x[0], y + 0.045, f["entity"], fontsize=7.5, color=WHITE,
                          transform=ax_table.transAxes, va="center")
            ax_table.text(col_x[1], y + 0.045, f["date"], fontsize=7, color=DIM,
                          transform=ax_table.transAxes, va="center")
            y -= row_h
    else:
        ax_table.text(0.5, 0.5, "No recent filings\nmatched query",
                      fontsize=9, color=DIM, transform=ax_table.transAxes,
                      ha="center", va="center")

    ax_table.text(0.5, 0.02, "EDGAR EFTS full-text search  |  Public filings only",
                  fontsize=6, color=GREY, transform=ax_table.transAxes,
                  ha="center", style="italic")

    # ── RIGHT: ENFORCEMENT SUMMARY ─────────────────────────────────────────────
    ax_stats.axis("off")
    ax_stats.set_title("Enforcement Summary", fontsize=9, color=DIM, pad=6)

    enf_rate_7d = enforcement.get("8k_enforcement_7d", 0)
    total_8k_7d = enforcement.get("8k_total_7d", 0)
    enf_pct = (enf_rate_7d / total_8k_7d * 100) if total_8k_7d > 0 else 0

    summary_rows = [
        ("Investigation 8-Ks (30d)",  str(enforcement.get("8k_investigation_30d", 0))),
        ("Subpoena/DOJ 8-Ks (30d)",   str(enforcement.get("8k_subpoena_30d", 0))),
        ("Enforcement-related (7d)",   str(enf_rate_7d)),
        ("Total 8-K Filings (7d)",     str(total_8k_7d)),
        ("Enforcement Rate (7d)",      f"{enf_pct:.1f}%"),
        ("S-1 Registrations (30d)",    str(enforcement.get("s1_filings_30d", 0))),
    ]

    row_h2 = 0.13
    y2 = 0.85
    for label, val in summary_rows:
        val_color = WHITE
        if "Investigation" in label or "Subpoena" in label or "Enforcement" in label:
            try:
                num = float(val.replace("%", ""))
                val_color = RED if num > 20 else (AMBER if num > 5 else GREEN)
            except ValueError:
                pass

        ax_stats.text(0.06, y2, label, fontsize=7.5, color=DIM,
                      transform=ax_stats.transAxes, va="top")
        ax_stats.text(0.94, y2, val, fontsize=8.5, color=val_color,
                      fontweight="bold", transform=ax_stats.transAxes,
                      ha="right", va="top")
        ax_stats.add_artist(plt.Line2D(
            [0.03, 0.97], [y2 - 0.015, y2 - 0.015],
            transform=ax_stats.transAxes, color="#1a1a4a", linewidth=0.5,
        ))
        y2 -= row_h2

    # Risk level indicator
    total_actions_val = enforcement.get("8k_investigation_30d", 0) + enforcement.get("8k_subpoena_30d", 0)
    risk_level = "ELEVATED" if total_actions_val > 30 else ("MODERATE" if total_actions_val > 10 else "LOW")
    risk_color = RED if risk_level == "ELEVATED" else (AMBER if risk_level == "MODERATE" else GREEN)

    y2 -= 0.05
    rect = FancyBboxPatch((0.03, y2 - 0.06), 0.94, 0.18,
                          boxstyle="round,pad=0.02",
                          facecolor="#1a1a4a", edgecolor=risk_color, linewidth=1,
                          transform=ax_stats.transAxes, clip_on=False)
    ax_stats.add_patch(rect)
    ax_stats.text(0.5, y2 + 0.04, f"Enforcement Activity: {risk_level}",
                  fontsize=9, color=risk_color, fontweight="bold",
                  transform=ax_stats.transAxes, ha="center", va="center")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    fig.text(0.02, 0.06,
             f"Source: SEC EDGAR (public filings)  |  Generated: {TIMESTAMP}",
             fontsize=7.5, color=GREY, va="top")
    fig.text(0.98, 0.06, "github.com/mboyajeffers/data-intelligence-platform",
             fontsize=7.5, color=INDIGO, va="top", ha="right")

    fig.add_artist(plt.Line2D([0.02, 0.98], [0.105, 0.105],
                              transform=fig.transFigure,
                              color="#1a1a4a", linewidth=0.8))

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close()
    print(f"Saved: {OUT_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching SEC EDGAR enforcement data...")
    enforcement, start_30d, end_str = fetch_enforcement_data()

    for k, v in enforcement.items():
        print(f"  {k}: {v}")

    print("Fetching notable enforcement filings...")
    filings = fetch_notable_enforcement(start_30d, end_str)
    print(f"  Found {len(filings)} recent investigation 8-Ks")

    print("Drawing card...")
    draw_card(enforcement, filings, start_30d, end_str)
    print("Done.")


if __name__ == "__main__":
    main()
