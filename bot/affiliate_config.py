"""
Affiliate Config — @Mboya_Jeffers X Bot
All monetization links, cashtags, CTAs, and thread reply content.

INSTRUCTIONS:
- Paste real affiliate URLs once approved (replace [PLACEHOLDER] strings)
- BIO_LINK: update after Beacons page is live
- FTC law: #ad required on every affiliate post ($50,120/violation without it)
  — REQUIRES_DISCLOSURE enforces this automatically in post.py

Priority affiliate order:
  1. Betway Affiliates   betway.com/affiliates         (1-3 day approval)
  2. BetMGM Partners     betmgmpartners.com             (hours-weeks)
  3. Hard Rock Bet       hardrock.bet/affiliates        (several days)
  4. Caesars Sportsbook  caesarspartners.com            (several days)

  (N1 Sport / PIN-UP / 1win World Cup-window affiliate offers expired
  July 19-20, 2026 — removed 2026-08-23, do not re-add without a new offer.)

Brokerage referral programs (flat bounty per funded account):
  1. Webull    webull.com/refer                        (days)
  2. Moomoo    moomoo.com/promotions/refer              (days)
  3. Robinhood robinhood.com/referral                   (days)
"""

# ── BIO LINK ───────────────────────────────────────────────────────────────────
# Update after Beacons page is live at beacons.ai
BIO_LINK = "beacons.ai/mboyajeffers"

# ── AFFILIATE HUB SITE ─────────────────────────────────────────────────────────
# VM-hosted, dedicated to the sportsbook/crypto/brokerage affiliate angle. Added
# 2026-08-26 because X's Paid Partnerships Policy (gambling banned Feb 2026;
# "financial products, services, or opportunities — including loans, investment
# services, and Crypto" banned Mar 2026) prohibits a sponsor-tagged affiliate
# link in an X post or reply for betting/crypto/brokerage/finance, regardless of
# whether X's own sponsorship-labeling tool is used. Those sponsor links now
# live only on this site; X posts for those verticals point here by topic only
# — no sponsor name, no #ad, since no compensation is disclosed on X itself.
# Paste the real VM URL once Phase 3 (deploy) is done.
AFFILIATE_SITE_URL = "[AFFILIATE_SITE_URL]"

# ── AFFILIATE URLS (paste real links after approval) ──────────────────────────
BETWAY_AFFILIATE_URL      = "[BETWAY_AFFILIATE_URL]"
BETMGM_AFFILIATE_URL      = "[BETMGM_AFFILIATE_URL]"
HARDROCKBET_AFFILIATE_URL = "[HARDROCKBET_AFFILIATE_URL]"
CAESARS_AFFILIATE_URL     = "[CAESARS_AFFILIATE_URL]"

# ── BROKERAGE REFERRAL URLS (paste real links after signup approval) ──────────
WEBULL_REFERRAL_URL     = "[WEBULL_REFERRAL_URL]"
MOOMOO_REFERRAL_URL     = "[MOOMOO_REFERRAL_URL]"
ROBINHOOD_REFERRAL_URL  = "[ROBINHOOD_REFERRAL_URL]"

# ── CRYPTO EXCHANGE REFERRAL (paste real link after signup approval) ──────────
# Kraken chosen over Coinbase 2026-08-24: Kraken pays ongoing revenue share
# (up to 50%, no time cap per referral); Coinbase caps its 50% commission to
# the first 3 months per referred user only. kraken.com/affiliate/apply
KRAKEN_AFFILIATE_URL    = "[KRAKEN_AFFILIATE_URL]"

# ── TRADING TOOLS REFERRAL (X-compliant — charting/analysis SaaS, not itself a
# broker/lender/exchange, so it sits outside the Mar 2026 "investment services"
# ban) ──────────────────────────────────────────────────────────────────────
# 30% recurring commission, 90-day cookie. tradingview.com/partner-rules
TRADINGVIEW_AFFILIATE_URL = "[TRADINGVIEW_AFFILIATE_URL]"

# ── CONTRA + LINKEDIN URLS (paste after listings go live) ─────────────────────
CONTRA_CANNABIS_URL    = "[CONTRA_CANNABIS_LISTING_URL]"   # paste after listing goes live
CONTRA_BETTING_URL     = "[CONTRA_BETTING_LISTING_URL]"    # paste after listing goes live
CONTRA_OAG_CUSTOM_URL  = "https://contra.com/s/YrQZvv2o-custom-oil-and-gas-intelligence-report-production-and-risk-48hr"
CONTRA_ENERGY_OAG_URL  = "https://contra.com/s/B2UWmOLQ-monthly-oil-and-gas-market-intelligence-dollar299mo"
LINKEDIN_URL           = "[LINKEDIN_PROFILE_URL]"          # paste now

# ── GUMROAD PRODUCTS ──────────────────────────────────────────────────────────
GUMROAD_SIGNAL_URL  = "https://jeffersmith4.gumroad.com/l/geikbo"
SIGNAL_PRICE        = "$300/mo"

# PASTE after creating Gumroad product: gumroad.com → Products → New → One-time → $29
GUMROAD_WC_REPORT_URL = "[GUMROAD_WC_REPORT_URL]"   # World Cup 2026 Sportsbook Report
WC_REPORT_PRICE       = "$29"

# PASTE after uploading Cannabis_Excise_Rate_Card.pdf to Gumroad as a $29 product
GUMROAD_CANNABIS_URL  = "[GUMROAD_CANNABIS_URL]"    # NY Cannabis Excise Rate Card + OCM Checklist
CANNABIS_EXCISE_PRICE = "$29"

# ── URL STATUS FLAGS — used for conditional fallbacks in thread replies ────────
_betway_live         = not BETWAY_AFFILIATE_URL.startswith("[")
_betmgm_live         = not BETMGM_AFFILIATE_URL.startswith("[")
_hardrockbet_live    = not HARDROCKBET_AFFILIATE_URL.startswith("[")
_caesars_live        = not CAESARS_AFFILIATE_URL.startswith("[")
_kraken_live         = not KRAKEN_AFFILIATE_URL.startswith("[")
_tradingview_live    = not TRADINGVIEW_AFFILIATE_URL.startswith("[")
_gumroad_wc_live     = not GUMROAD_WC_REPORT_URL.startswith("[")
_contra_betting_live = not CONTRA_BETTING_URL.startswith("[")
_webull_live         = not WEBULL_REFERRAL_URL.startswith("[")
_moomoo_live         = not MOOMOO_REFERRAL_URL.startswith("[")
_robinhood_live      = not ROBINHOOD_REFERRAL_URL.startswith("[")
_broker_referral_live = _webull_live or _moomoo_live or _robinhood_live
# Priority order when more than one broker referral is live: Webull > Moomoo > Robinhood
_broker_referral_url = (
    WEBULL_REFERRAL_URL if _webull_live
    else MOOMOO_REFERRAL_URL if _moomoo_live
    else ROBINHOOD_REFERRAL_URL if _robinhood_live
    else None
)

# Ordered by the priority list documented at the top of this file. Any subset
# can be live at once (approval timing differs per program) — the helper
# below joins whichever ones are actually live instead of gating on all of
# them being live together. (Bug this replaces, fixed 2026-08-24: the betting
# thread reply required Betway AND BetMGM both live before showing either;
# finance/brokerage/media only ever checked Betway alone, so a BetMGM-only,
# Hard Rock-only, or Caesars-only approval activated nothing anywhere.)
_SPORTSBOOK_AFFILIATES = [
    ("Betway",     BETWAY_AFFILIATE_URL,      _betway_live),
    ("BetMGM",     BETMGM_AFFILIATE_URL,      _betmgm_live),
    ("Hard Rock",  HARDROCKBET_AFFILIATE_URL, _hardrockbet_live),
    ("Caesars",    CAESARS_AFFILIATE_URL,     _caesars_live),
]
_sportsbook_live = any(is_live for _, _, is_live in _SPORTSBOOK_AFFILIATES)


def _sportsbook_promo_line(prefix="Best promos"):
    """Join whichever sportsbook affiliate links are currently live.
    Returns None if none are live yet — caller falls back to BIO_LINK."""
    live = [(name, url) for name, url, is_live in _SPORTSBOOK_AFFILIATES if is_live]
    if not live:
        return None
    if len(live) == 1:
        return f"{prefix} → {live[0][1]}"
    return f"{prefix}: " + " | ".join(f"{name} → {url}" for name, url in live)

# ── CASHTAGS PER VERTICAL (2-3x organic reach boost) ─────────────────────────
# X Free tier: 1 cashtag per tweet max — one primary ticker per vertical
VERTICAL_CASHTAGS = {
    "finance":    "$SPY",
    "crypto":     "$BTC",
    "brokerage":  "$GS",
    "betting":    "$DKNG",
    "gaming":     "$TTWO",
    "ecommerce":  "$AMZN",
    "media":      "$NFLX",
    "oilgas":     "$XLE",
    "solar":      "$FSLR",
    "worldcup":   "",       # worldcup caption manages its own single $DKNG
    "compliance": "",
    "weather":    "",
    "cannabis":   "$MJ",
    "insight":    "",       # organic text post — no cashtag
    "signal":     "",       # outcome card — no cashtag (not a sector post)
}

# ── CTAs (replace hashtags in captions — drives bio clicks) ───────────────────
_contra_cannabis_live = not CONTRA_CANNABIS_URL.startswith("[")
_gumroad_cannabis_live = not GUMROAD_CANNABIS_URL.startswith("[")

VERTICAL_CTA = {
    # betting: no sponsor tag on X (gambling banned from paid partnerships Feb
    # 2026) — sportsbook comparison + real affiliate links live on the site only.
    "betting":    f"Full sportsbook sector breakdown → {AFFILIATE_SITE_URL}",
    # crypto/brokerage/finance: no exchange/broker sponsor tag on X (banned Mar
    # 2026) — but TradingView (charting tool, not a broker/exchange) stays
    # compliant, so it's the live CTA here once approved; falls back to a
    # neutral site pointer (no sponsor, no #ad) until then.
    "crypto": (
        f"Chart it free → {TRADINGVIEW_AFFILIATE_URL}"
        if _tradingview_live
        else f"Full on-chain + market data → {AFFILIATE_SITE_URL}"
    ),
    "brokerage": (
        f"Chart these stocks free → {TRADINGVIEW_AFFILIATE_URL}"
        if _tradingview_live
        else f"Full broker sector data → {AFFILIATE_SITE_URL}"
    ),
    "finance": (
        f"Chart this data free → {TRADINGVIEW_AFFILIATE_URL}"
        if _tradingview_live
        else f"Full sector data + market tools → {AFFILIATE_SITE_URL}"
    ),
    "solar":      f"Live solar sector data → {BIO_LINK}",
    "ecommerce":  f"Live retail sector data → {BIO_LINK}",
    "gaming":     f"Gaming sector data this week → {BIO_LINK}",
    # media: no sponsor tag on X — same reasoning as betting.
    "media":      f"Full broadcast + sector data → {AFFILIATE_SITE_URL}",
    "oilgas":     f"Custom O&G intelligence report $499 → {CONTRA_OAG_CUSTOM_URL}",
    "worldcup": (
        f"Full WC Sportsbook Report {WC_REPORT_PRICE} → {GUMROAD_WC_REPORT_URL}  Best promos → {BIO_LINK}"
        if _gumroad_wc_live
        else f"World Cup sportsbook data + analysis → {BIO_LINK}"
    ),
    "compliance": f"SEC enforcement data → {BIO_LINK}",
    "weather":    f"Full US weather data → {BIO_LINK}",
    # Cannabis CTA: live Contra URL → use it; else fall back to bio link
    "cannabis": (
        f"NYC dispensary analytics → {CONTRA_CANNABIS_URL}"
        if _contra_cannabis_live
        else f"NYC dispensary 280E + compliance analytics → {BIO_LINK}"
    ),
    "insight":    "",       # no CTA — post stands alone as organic content
    "signal":     f"Morning Signals {SIGNAL_PRICE} → {GUMROAD_SIGNAL_URL}",
}

# ── THREAD REPLIES ─────────────────────────────────────────────────────────────
# Posted 90 min AFTER main tweet via post_thread_reply.py (separate cron).
# The 90-min gap lets the main tweet accumulate early engagement before the
# reply appears — simultaneous replies suppress main tweet organic reach.
# FTC law: #ad required on every affiliate post.
# None = no thread reply for that vertical.

THREAD_REPLIES = {
    # worldcup: dynamic — post_thread_reply.py fetches live stock returns at post time
    # so "$PENN +X%" is always current, never stale.
    "worldcup": "__DYNAMIC__",
    # betting: no sponsor tag on X (gambling banned from paid partnerships) —
    # sportsbook comparison + real affiliate links live on the site only.
    "betting": (
        "I track the full sportsbook sector daily — handle trends, "
        "regulatory pipeline, stock performance vs. SPY.\n\n"
        + (f"Monthly intel → {CONTRA_BETTING_URL}\n\n" if _contra_betting_live
           else f"Monthly intel → {BIO_LINK}\n\n")
        + f"Full sportsbook comparison → {AFFILIATE_SITE_URL}"
    ),
    "cannabis": (
        "NYC dispensaries get hit twice: 280E kills normal federal "
        "deductions, and NY's potency-tier excise is calculated wrong "
        "by most POS systems.\n\n"
        "I track both monthly.\n\n"
        "$29 rate card / $399 full report / $697 monthly\n\n"
        + (f"{CONTRA_CANNABIS_URL}" if _contra_cannabis_live
           else f"Rate card → {GUMROAD_CANNABIS_URL}" if _gumroad_cannabis_live
           else f"Full product line → {BIO_LINK}")
    ),
    # media: no sponsor tag on X — same reasoning as betting.
    "media": (
        "FOX paid $485M for World Cup broadcast rights ($FOX).\n"
        "$CMCSA holds Spanish rights via Telemundo.\n\n"
        "Sportsbook and broadcast sector data, full breakdown:\n"
        f"{AFFILIATE_SITE_URL}"
    ),
    # finance/brokerage: no exchange/broker sponsor tag on X — the TradingView
    # CTA already runs in the main caption, so the reply stays neutral rather
    # than repeating a sponsor mention twice in one thread.
    "finance": (
        "I track 22 finance KPIs daily across 11 sectors.\n\n"
        f"Full sector data + sportsbook/crypto/broker breakdown → {AFFILIATE_SITE_URL}"
    ),
    "brokerage": (
        "I track broker sector data weekly ($GS $MS $SCHW).\n\n"
        f"Full broker + sportsbook sector breakdown → {AFFILIATE_SITE_URL}"
    ),
    # crypto thread reply is built live at post time — fetches MVRV, F&G, Aave TVL from APIs
    "crypto": "__DYNAMIC__",
    "solar":      None,  # No audience-matched affiliate yet
    "ecommerce":  None,  # Audience mismatch confirmed
    "gaming":     None,  # No strong affiliate angle
    "oilgas": (
        "I track US crude and natural gas production from EIA monthly data "
        "— production trends, price volatility, and revenue at risk.\n\n"
        "Two ways to get it:\n\n"
        f"One-time custom report (48hr) $499 → {CONTRA_OAG_CUSTOM_URL}\n\n"
        f"Monthly intelligence brief $299/mo → {CONTRA_ENERGY_OAG_URL}"
    ),
    "compliance": None,
    "weather":    None,
    "insight":    None,  # text-only organic post — no thread reply
    "signal":     None,  # outcome card stands alone — no thread reply needed
}

# Verticals with affiliate content — #ad is required by FTC on every post.
# cannabis is NOT here — no affiliate link in caption, no #ad needed.
#
# Rewritten 2026-08-26: betting/media/worldcup dropped — X's Paid Partnerships
# Policy (gambling banned Feb 2026) means these verticals can never carry a
# sponsor tag on X again, by design (see AFFILIATE_SITE_URL note above), so
# there's nothing left to disclose. finance/brokerage/crypto stay listed
# pre-emptively (same reasoning as the original 2026-08-23 crypto entry this
# replaces) so the TradingView CTA can't ship without #ad by oversight once
# TRADINGVIEW_AFFILIATE_URL goes live.
REQUIRES_DISCLOSURE = {
    "finance", "brokerage", "crypto"
}
