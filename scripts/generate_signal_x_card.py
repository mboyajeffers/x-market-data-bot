#!/usr/bin/env python3
"""
Signal Outcome Card — 4:15PM ET daily.

Reads today's signals from last_signal.json (synced from VM).
Shows: ticker, direction, confidence, entry price, EOD price, result.
Teaser for Gumroad subscribers — proof-of-work content funnel.

Output: REVENUE/X/cards/signal_x_card_YYYY-MM-DD.png (1200x675px)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import yfinance as yf

# local imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from card_spec import (  # noqa: E402
    FONT_TITLE, FONT_HEADLINE, FONT_LABEL, FONT_SMALL, FONT_TINY,
    GS_TOP, HDR_TITLE_Y, HDR_HEADLINE_Y, FOOTER_Y, MARGIN_LEFT, MARGIN_RIGHT,
)
from card_validator import detect_and_fix_overlaps  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "bot"))
from affiliate_config import GUMROAD_SIGNAL_URL, SIGNAL_PRICE  # noqa: E402

# ─── PATHS & CONFIG ───────────────────────────────────────────────────────────

OUT_DIR       = Path(__file__).parent.parent / "cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY         = date.today().isoformat()
TIMESTAMP     = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
OUT_PATH      = OUT_DIR / f"signal_x_card_{TODAY}.png"

# VM fetch is optional and config-driven — unset in any environment (e.g. GitHub
# Actions) that shouldn't know the private VM's name/project, and the script
# just falls back to the local copy synced by another process.
VM_NAME        = os.environ.get("SIGNAL_VM_NAME")
VM_PROJECT     = os.environ.get("SIGNAL_VM_PROJECT")
VM_SIGNAL_PATH = os.environ.get("SIGNAL_VM_REMOTE_PATH", "")
LOCAL_SIGNAL   = Path(__file__).parent.parent / "data" / "last_signal.json"

# ─── COLORS ───────────────────────────────────────────────────────────────────

BG           = "#0a0e14"   # bg-primary
CARD_BG      = "#1a2130"   # bg-card
BORDER       = "#2a3441"   # border-color
ACCENT       = "#00d4aa"   # accent-cyan
GRADIENT_A   = "#00d4aa"   # gradient-1 start
GRADIENT_B   = "#3b82f6"   # gradient-1 end
GREEN        = "#22c55e"   # accent-green (LONG)
RED          = "#ef4444"   # accent-red (SHORT)
AMBER        = "#f59e0b"   # amber
WHITE        = "#f1f5f9"   # text-primary
DIM          = "#94a3b8"   # text-secondary
GREY         = "#64748b"   # text-muted
PANEL_BORDER = "#00d4aa"   # alias

# ─── SIGNAL FETCH ─────────────────────────────────────────────────────────────

def fetch_signal_from_vm() -> dict:
    """SCP last_signal.json from the VM if configured. Falls back to local copy
    (and, in environments with no VM access configured — e.g. GitHub Actions —
    skips the fetch entirely rather than shelling out with nothing to reach)."""
    LOCAL_SIGNAL.parent.mkdir(parents=True, exist_ok=True)
    if VM_NAME and VM_PROJECT and VM_SIGNAL_PATH:
        try:
            result = subprocess.run(
                [
                    "gcloud", "compute", "scp",
                    f"{VM_NAME}:{VM_SIGNAL_PATH}",
                    str(LOCAL_SIGNAL),
                    "--zone=us-central1-a",
                    f"--project={VM_PROJECT}",
                    "--tunnel-through-iap",
                ],
                capture_output=True, timeout=30
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode())
            print("Fetched last_signal.json from VM")
        except Exception as e:
            print(f"VM fetch failed ({e}), using local copy")

    if LOCAL_SIGNAL.exists():
        return json.loads(LOCAL_SIGNAL.read_text())
    return {}


def get_entry_and_eod_price(symbol: str) -> tuple:
    """Return (open_price, close_price) for today. Falls back to yesterday close if market closed."""
    try:
        hist = yf.Ticker(symbol).history(period="2d")
        if hist.empty:
            return None, None
        row = hist.iloc[-1]
        return float(row['Open']), float(row['Close'])
    except Exception:
        return None, None


# ─── CARD DRAW ────────────────────────────────────────────────────────────────

def build_card(signal_data: dict) -> Path:
    signals  = signal_data.get('signals', [])
    regime   = signal_data.get('regime', 'UNKNOWN')
    vix      = signal_data.get('vix', 0.0)
    sig_date = signal_data.get('date', TODAY)
    blocked  = signal_data.get('blocked', False)

    fig = plt.figure(figsize=(12, 6.75), facecolor=BG)

    # ── Full background gradient overlay (subtle deep blue-to-black) ──────────
    ax_bg = fig.add_axes([0, 0, 1, 1], zorder=0)
    ax_bg.set_facecolor(BG)
    ax_bg.imshow([[0, 0], [1, 1]], aspect='auto', extent=[0, 1, 0, 1],
                 cmap=plt.cm.Blues, alpha=0.06, zorder=0)
    ax_bg.set_xticks([]); ax_bg.set_yticks([])
    for sp in ax_bg.spines.values(): sp.set_visible(False)

    # ── Header ────────────────────────────────────────────────────────────────
    title_str = f"Morning Signals — {sig_date}"
    _regime_color = GREEN if regime == 'CLEAR' else AMBER if regime == 'WARNING' else RED

    # Title — centered, clean white
    fig.text(0.5, HDR_TITLE_Y, title_str,
             color=WHITE, fontsize=FONT_TITLE, fontweight='bold',
             transform=fig.transFigure, va='top', ha='center')

    # Regime line — centered below title
    fig.text(0.5, HDR_HEADLINE_Y,
             f"Regime: {regime}  |  VIX {vix:.1f}  |  @Mboya_Jeffers",
             color=ACCENT, fontsize=FONT_SMALL, transform=fig.transFigure,
             va='top', ha='center', alpha=0.85)

    # ── Separator — gradient-1 style strip ────────────────────────────────
    ax_line = fig.add_axes([MARGIN_LEFT, GS_TOP + 0.01, MARGIN_RIGHT - MARGIN_LEFT, 0.002])
    ax_line.set_facecolor(ACCENT)
    ax_line.set_alpha(0.55)
    ax_line.set_xticks([]); ax_line.set_yticks([])
    for spine in ax_line.spines.values():
        spine.set_visible(False)

    # ── Content area ──────────────────────────────────────────────────────────
    if blocked or not signals:
        # No-signal card
        ax = fig.add_axes([0.05, 0.22, 0.90, 0.55])
        ax.set_facecolor(CARD_BG)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color(PANEL_BORDER)

        msg = "No high-confidence signals today." if not blocked else \
              f"Signals BLOCKED — {signal_data.get('blocked_reason', 'regime filter')}"

        ax.text(0.5, 0.62, msg, color=WHITE, fontsize=FONT_HEADLINE,
                ha='center', va='center', transform=ax.transAxes, fontweight='bold')
        ax.text(0.5, 0.40, f"Regime: {regime}  |  VIX {vix:.1f}",
                color=DIM, fontsize=FONT_LABEL, ha='center', va='center',
                transform=ax.transAxes)
        ax.text(0.5, 0.22,
                f"Subscribe: {GUMROAD_SIGNAL_URL}",
                color=ACCENT, fontsize=FONT_SMALL, ha='center', va='center',
                transform=ax.transAxes)

    else:
        # Signal result cards
        n = len(signals)
        pad_l = 0.04
        col_w = (0.92) / n
        col_gap = 0.012

        for i, sig in enumerate(signals):
            symbol    = sig['symbol']
            direction = sig['direction']  # 'LONG' or 'SHORT'
            conf      = sig['confidence']
            reasoning = sig.get('reasoning', 'Technical setup')
            is_strong = sig.get('strong', False)

            entry_px, eod_px = get_entry_and_eod_price(symbol)
            if entry_px and eod_px:
                raw_return = (eod_px - entry_px) / entry_px * 100
                actual_return = raw_return if direction == 'LONG' else -raw_return
                result_str = f"{'+' if actual_return >= 0 else ''}{actual_return:.1f}%"
                result_color = GREEN if actual_return >= 0 else RED
                price_str = f"Entry ${entry_px:.2f}  →  EOD ${eod_px:.2f}"
            else:
                actual_return = None
                result_str = "Market closed"
                result_color = DIM
                price_str = "Price pending"

            direction_color = GREEN if direction == 'LONG' else RED
            direction_arrow = '▲' if direction == 'LONG' else '▼'

            # Card panel — design system (bg-card + subtle accent, no solid header)
            x0 = pad_l + i * (col_w + col_gap)
            card_h = 0.63

            # Outer glow: very thin ring at 12% alpha (page hover: box-shadow 0 0 20px)
            glow_pad = 0.003
            ax_outer = fig.add_axes(
                [x0 - glow_pad, 0.15 - glow_pad,
                 col_w - col_gap * 0.5 + glow_pad * 2,
                 card_h + glow_pad * 2], zorder=1
            )
            ax_outer.set_facecolor('none')
            ax_outer.set_xticks([]); ax_outer.set_yticks([])
            for sp in ax_outer.spines.values():
                sp.set_color(direction_color)
                sp.set_linewidth(5)
                sp.set_alpha(0.12)

            # Card — bg-card background, 1px colored border (.sku-card hover style)
            ax = fig.add_axes([x0, 0.15, col_w - col_gap * 0.5, card_h], zorder=2)
            ax.set_facecolor(CARD_BG)
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color(direction_color)
                spine.set_linewidth(1.2)
                spine.set_alpha(0.65)

            # 3px accent strip at top (pricing-card ::before gradient)
            strip = FancyBboxPatch((0, 0.968), 1.0, 0.032,
                                   boxstyle="square,pad=0",
                                   facecolor=direction_color, linewidth=0,
                                   transform=ax.transAxes, zorder=3, alpha=0.85)
            ax.add_patch(strip)

            # Ticker — large monospace white, below the strip
            ax.text(0.5, 0.875, symbol,
                    color=WHITE, fontsize=FONT_TITLE + 2, fontweight='bold',
                    ha='center', va='center', transform=ax.transAxes,
                    fontfamily='monospace')

            # Direction badge — pill style (.hero-badge / .pricing-badge)
            conf_label = "HIGH" if is_strong else "MED"
            badge = FancyBboxPatch((0.08, 0.75), 0.84, 0.095,
                                   boxstyle="round,pad=0.015",
                                   facecolor=direction_color, alpha=0.12,
                                   edgecolor=direction_color, linewidth=0.7,
                                   transform=ax.transAxes, zorder=3)
            ax.add_patch(badge)
            ax.text(0.5, 0.795,
                    f"{direction_arrow} {direction}  [{conf_label} {conf:.0%}]",
                    color=direction_color, fontsize=FONT_HEADLINE,
                    ha='center', va='center', fontweight='bold',
                    transform=ax.transAxes)

            # Return — dominant number (.stat-value style)
            result_fs = FONT_TITLE + 5 if actual_return is not None else FONT_HEADLINE
            ax.text(0.5, 0.590, result_str,
                    color=result_color, fontsize=result_fs,
                    ha='center', va='center', fontweight='bold',
                    transform=ax.transAxes, fontfamily='monospace')

            # Entry → EOD — text-secondary muted
            ax.text(0.5, 0.445, price_str,
                    color=DIM, fontsize=FONT_SMALL,
                    ha='center', va='center', transform=ax.transAxes)

            # Divider — border-color
            ax.axhline(0.365, color=BORDER, linewidth=0.9, alpha=1.0)

            # Reasoning — accent cyan (.sku-turnaround color)
            ax.text(0.5, 0.225, reasoning,
                    color=ACCENT, fontsize=FONT_TINY, alpha=0.88,
                    ha='center', va='center',
                    transform=ax.transAxes,
                    multialignment='center')

        # CTA strip — glowing cyan text
        fig.text(0.5, 0.10,
                 f"Get tomorrow's signals pre-market  ·  {SIGNAL_PRICE}  ·  {GUMROAD_SIGNAL_URL}",
                 color=ACCENT, fontsize=FONT_SMALL, ha='center',
                 transform=fig.transFigure, fontweight='bold')

    # ── Footer ────────────────────────────────────────────────────────────────
    fig.text(MARGIN_LEFT, FOOTER_Y,
             "Not investment advice. For informational purposes only.",
             color=GREY, fontsize=FONT_TINY, transform=fig.transFigure, va='top')
    fig.text(MARGIN_RIGHT, FOOTER_Y, TIMESTAMP,
             color=GREY, fontsize=FONT_TINY, ha='right',
             transform=fig.transFigure, va='top')

    detect_and_fix_overlaps(fig)

    plt.savefig(str(OUT_PATH), dpi=200, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    print(f"Signal card saved: {OUT_PATH}")
    return OUT_PATH


# ─── CAPTION ──────────────────────────────────────────────────────────────────

def build_caption(signal_data: dict) -> str:
    signals = signal_data.get('signals', [])
    regime  = signal_data.get('regime', 'CLEAR')

    if not signals:
        return (
            f"No signals cleared the confidence bar today.\n\n"
            f"Regime: {regime}. The model only flags setups it believes in.\n\n"
            f"Subscribers get pre-market alerts when it does fire.\n"
            f"{GUMROAD_SIGNAL_URL}\n\n"
            f"#QuantTrading #Signals"
        )

    lines = []
    for s in signals:
        arrow = '▲' if s['direction'] == 'LONG' else '▼'
        lines.append(f"{s['symbol']} {arrow} {s['direction']} [{s['confidence']:.0%}]")

    signal_list = "  ·  ".join(lines)
    return (
        f"Today's signals: {signal_list}\n\n"
        f"Flagged pre-market at 6:15am. Powered by point-in-time fundamentals "
        f"and walk-forward validation.\n\n"
        f"Subscribers got these before open.\n"
        f"{GUMROAD_SIGNAL_URL}\n\n"
        f"#QuantTrading #SwingTrading #Signals"
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--local', action='store_true', help='Use local last_signal.json (no VM fetch)')
    parser.add_argument('--caption-only', action='store_true', help='Print caption only')
    args = parser.parse_args()

    if args.local and LOCAL_SIGNAL.exists():
        signal_data = json.loads(LOCAL_SIGNAL.read_text())
    else:
        signal_data = fetch_signal_from_vm()

    if not signal_data:
        print("No signal data available — generating empty card")
        signal_data = {'signals': [], 'regime': 'UNKNOWN', 'vix': 0.0,
                       'date': TODAY, 'blocked': False}

    caption = build_caption(signal_data)

    if args.caption_only:
        print(caption)
        return

    card_path = build_card(signal_data)
    print("\n--- Caption ---")
    print(caption)
    print(f"\nCard: {card_path}")


if __name__ == '__main__':
    main()
