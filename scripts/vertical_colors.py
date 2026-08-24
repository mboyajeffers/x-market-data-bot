"""
Canonical color scheme for every X card vertical.
Single source of truth — edit here, not in individual generators.

Base palette (shared by all verticals):
  BG           #0a0e14   site --bg-primary
  PANEL        #1a2130   site --bg-card
  DARK         #121820   site --bg-secondary
  BORDER       #2a3441   site --border-color
  TEXT         #f1f5f9   site --text-primary
  DIM          #94a3b8   site --text-secondary
  MUTED        #64748b   site --text-muted
  POS_GREEN    #22c55e   positive values (universal)
  NEG_RED      #ef4444   negative values (universal)
  WARN_AMBER   #f59e0b   warning / neutral highlight

Vertical accent = the gradient stripe colour + section-tag + primary highlights.
  accent  = bright version (used on dark bg for text, borders, tags)
  accent2 = darker/paired version (used as gradient end)
  grad    = CSS/description gradient (start → end)
"""

# ── SHARED BASE ───────────────────────────────────────────────────────────────
BASE = {
    "bg":           "#0a0e14",   # --bg-primary
    "panel":        "#1a2130",   # --bg-card
    "dark":         "#121820",   # --bg-secondary
    "border":       "#2a3441",   # --border-color
    "text":         "#f1f5f9",   # --text-primary
    "dim":          "#94a3b8",   # --text-secondary
    "muted":        "#64748b",   # --text-muted
    "pos":          "#22c55e",   # positive / gain
    "neg":          "#ef4444",   # negative / loss
    "warn":         "#f59e0b",   # warning / neutral accent
}

# ── PER-VERTICAL ACCENT COLOURS ───────────────────────────────────────────────
VERTICAL = {
    # accent  = bright colour used for headers, section tags, highlights on dark bg
    # accent2 = paired colour (gradient partner or secondary highlight)
    # grad    = gradient description (accent2 → accent), used on stripe + bars
    "worldcup": {
        "accent":  "#00d4aa",   # brand cyan
        "accent2": "#3b82f6",   # brand blue
        "grad":    ("#00d4aa", "#3b82f6"),  # site signature
    },
    "betting": {
        "accent":  "#22c55e",   # CLAUDE.md betting #16a34a, brightened for dark bg
        "accent2": "#14b8a6",   # teal partner
        "grad":    ("#16a34a", "#22c55e"),
    },
    "finance": {
        "accent":  "#3b82f6",   # CLAUDE.md #1e3a5f → bright blue on dark bg
        "accent2": "#1e3a5f",
        "grad":    ("#1e3a5f", "#3b82f6"),
    },
    "brokerage": {
        "accent":  "#f59e0b",   # gold — Wall Street / wealth management
        "accent2": "#1e3a5f",   # navy depth (CLAUDE.md primary)
        "grad":    ("#1e3a5f", "#f59e0b"),
    },
    "media": {
        "accent":  "#2563eb",   # CLAUDE.md #2563eb
        "accent2": "#60a5fa",   # bright blue secondary
        "grad":    ("#1e3c7c", "#2563eb"),
    },
    "ecommerce": {
        "accent":  "#d97706",   # CLAUDE.md #d97706 amber-orange
        "accent2": "#f59e0b",
        "grad":    ("#92400e", "#d97706"),
    },
    "gaming": {
        "accent":  "#db2777",   # CLAUDE.md #db2777 pink/magenta
        "accent2": "#9333ea",   # purple secondary
        "grad":    ("#9d174d", "#db2777"),
    },
    "crypto": {
        "accent":  "#a855f7",   # CLAUDE.md #9333ea family, bright purple
        "accent2": "#581c87",
        "grad":    ("#581c87", "#a855f7"),
    },
    "solar": {
        "accent":  "#ca8a04",   # CLAUDE.md #ca8a04 golden
        "accent2": "#713f12",
        "grad":    ("#713f12", "#ca8a04"),
    },
    "oilgas": {
        "accent":  "#c2410c",   # CLAUDE.md #c2410c burnt orange
        "accent2": "#7c2d12",
        "grad":    ("#7c2d12", "#c2410c"),
    },
    "compliance": {
        "accent":  "#818cf8",   # CLAUDE.md #4f46e5 → bright indigo on dark bg
        "accent2": "#2e1065",
        "grad":    ("#2e1065", "#4f46e5"),
    },
    "cannabis": {
        "accent":  "#f59e0b",   # gold — premium dispensary analytics (matches PDF branding)
        "accent2": "#92400e",
        "grad":    ("#92400e", "#f59e0b"),
    },
    "weather": {
        "accent":  "#06b6d4",   # sky cyan — atmosphere / data
        "accent2": "#164e63",
        "grad":    ("#164e63", "#06b6d4"),
    },
}
