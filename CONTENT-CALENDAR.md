# Content calendar: first 12 weeks

Theme rotation lives in `pipeline/config/theme-rotation.yaml`. The Scout agent reads this every Wednesday to know what to source. You can edit themes freely without touching code.

Pattern: week 1 halal-French fusion, week 2 healthy weeknight, week 3 Mediterranean light, week 4 subcontinental heritage. Repeat. Adjust after week 12 based on what ranked.

## Q1 starter (weeks 1–12)

| Wk | Sat date 2026 | Theme | Working title | Why this one |
|----|---------------|-------|---------------|--------------|
| 1 | 2026-05-16 | Halal-French fusion | Lamb shank tagine with herbes de Provence | Hits the niche thesis head-on. Visually strong. |
| 2 | 2026-05-23 | Healthy weeknight | 20-minute chicken shawarma bowl | High search volume, fast prep, photo-friendly. |
| 3 | 2026-05-30 | Mediterranean light | Whole roasted branzino with preserved lemon | French technique, Mediterranean cuisine, halal-by-default. |
| 4 | 2026-06-06 | Subcontinental heritage | Karahi gosht — proper Lahori technique | Heritage post. Strong story angle. |
| 5 | 2026-06-13 | Halal-French fusion | Halal coq au vin (verjus instead of wine) | Direct answer to a real search query. |
| 6 | 2026-06-20 | Healthy weeknight | Sheet-pan harissa salmon with chickpeas | Summer Saturday cooking. |
| 7 | 2026-06-27 | Mediterranean light | Greek-style stuffed peppers (gemista) | Vegetarian week. Broadens audience. |
| 8 | 2026-07-04 | Subcontinental heritage | Bhuna gosht — slow-cooked Punjabi mutton | Eid-adjacent timing if applicable. |
| 9 | 2026-07-11 | Halal-French fusion | Beef bourguignon with grape juice reduction | The technique flagship post. |
| 10 | 2026-07-18 | Healthy weeknight | Lebanese-style grilled chicken with toum | Summer grilling season. |
| 11 | 2026-07-25 | Mediterranean light | Turkish kuru fasulye (white bean stew) | Pantry cooking, holiday-friendly. |
| 12 | 2026-08-01 | Subcontinental heritage | Sindhi biryani — distinct from Hyderabadi | Niche term, low competition. |

## Why this mix works

Variety across the month keeps the audience broad. Each week has a clear search intent (specific dish name) plus a technique angle. None of these are over-served by existing English-language food blogs; all have French or Pakistani cultural cred only you can credibly bring.

The Scout agent will produce 5 candidates per theme; you (or the auto-selector by SEO score) pick which one ships.

## Heritage weeks are special

Weeks 4, 8, 12 (subcontinental heritage) get extra editorial attention. The headnote should reference real memory or family practice. The Writer prompt has a flag for this; toggled on in `config/theme-rotation.yaml` for those weeks. These are the posts that will pull diaspora audiences and earn the strongest emotional engagement on social.

## After week 12

Audit Saturday morning week 13. The Archivist's quarterly digest gives:

- Top 3 posts by Google impressions
- Top 3 posts by Pinterest saves
- Top 3 posts by email click-throughs
- Posts with zero traction (kill the theme)
- Search Console queries we are almost ranking for (chase those)

Rewrite the next 12 weeks of themes accordingly. The pipeline does not change. Only the prompts and themes do.
