"""
X Card Unified Sizing Spec
Single source of truth for all matplotlib card generators.
Import with: from card_spec import *
"""

# ── FONT SIZES ────────────────────────────────────────────────────────────────
# Scaled for readability at 1200px display width on X (desktop + mobile)

FONT_TITLE    = 22    # Main header title
FONT_HEADLINE = 15    # Dynamic insight line
FONT_STAT     = 13    # Key stat top-right (SPY/VIX/Fear & Greed)
FONT_HANDLE   = 13    # @Mboya_Jeffers attribution
FONT_LABEL    = 12    # Chart axis tick labels, table row labels
FONT_VALUE    = 11    # Table values, bar annotations, movers pct
FONT_SMALL    = 9     # Secondary labels, movers sector names
FONT_TINY     = 8     # Footer source/timestamp line
FONT_MICRO    = 7     # Absolute floor — auto-adjuster never goes below this

# ── GRIDSPEC LAYOUT ───────────────────────────────────────────────────────────
# More vertical breathing room so larger fonts don't crowd the content area

GS_TOP    = 0.76    # Content area top (was 0.82 — 6% more header room)
GS_BOTTOM = 0.16    # Content area bottom (was 0.13 — more footer room)
GS_LEFT   = 0.02
GS_RIGHT  = 0.98
GS_WSPACE = 0.32    # Default horizontal spacing between panels

# ── HEADER Y-POSITIONS ────────────────────────────────────────────────────────
# Figure coordinates. Designed so no two elements at the same x-side overlap.

HDR_TITLE_Y    = 0.955   # Left — main title "Market Snapshot — DATE"
HDR_HEADLINE_Y = 0.875   # Left — dynamic insight line (80px gap below title)
HDR_STAT_Y     = 0.950   # Right — key stat line (SPY/VIX etc.)
HDR_HANDLE_Y   = 0.893   # Right — @Mboya_Jeffers (guaranteed gap below stat)
FOOTER_Y       = 0.065   # Both sides — footer source line
FOOTER_LINE_Y  = 0.112   # Horizontal separator line above footer

# ── MARGINS ───────────────────────────────────────────────────────────────────
MARGIN_LEFT  = 0.03
MARGIN_RIGHT = 0.97
