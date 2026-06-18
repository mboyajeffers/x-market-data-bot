# X Posting Schedule — @Mboya_Jeffers

## Weekly Rhythm

| Day | Time (ET) | Post Type | Action Required |
|-----|-----------|-----------|-----------------|
| **Monday** | 9:00 AM | Finance card | Run `generate_finance_x_card.py` → post image + caption |
| **Wednesday** | varies | Engagement (optional) | Reply to industry posts, quote tweet relevant analytics content |
| **Thursday** | 9:00 AM | Crypto card | Run `generate_crypto_x_card.py` → post image + caption |
| **Friday** | varies | Text thread (optional) | System insight or case study from Thread Templates |

---

## Pre-Post Checklist

Before each Mon/Thu post:
- [ ] Run the relevant script from `REVENUE/X/scripts/`
- [ ] Verify PNG loaded correctly (non-zero file size, data looks current)
- [ ] Fill in the caption template with actual values from the card
- [ ] Schedule or post at 9:00 AM ET

---

## Engagement Protocol

**Within 2 hours of posting:**
- Reply to all comments
- Like replies
- Follow back relevant data/finance/tech accounts

**Mid-week (Wed):**
- Search X for: `#DataEngineering`, `#FinanceData`, `#CryptoData`, `#Analytics`
- Engage with 3–5 posts: thoughtful replies (not just "great post!")
- Quote tweet 1 relevant piece of content if strong enough

---

## Monthly Cadence

| Week | Focus |
|------|-------|
| Week 1 | Launch + finance + crypto cards |
| Week 2 | Finance + crypto cards + 1 text thread |
| Week 3 | Finance + crypto cards |
| Week 4 | Finance + crypto cards + case study thread |

---

## Metrics to Track (monthly review)

- Impressions per card post
- Follows gained per post type (image vs text)
- Profile visits from X
- Link clicks to GitHub
- DMs received (potential leads)

---

## Script Locations

```bash
# Run before every post
cd /Users/mboyajeffers/Claude_Projects/REVENUE/X/scripts

# Monday
python3 generate_finance_x_card.py
# Output: ../cards/finance_x_card_YYYY-MM-DD.png

# Thursday
python3 generate_crypto_x_card.py
# Output: ../cards/crypto_x_card_YYYY-MM-DD.png

# Header (one-time, or to refresh)
python3 generate_x_header.py
# Output: ../cards/x_header.png
```
