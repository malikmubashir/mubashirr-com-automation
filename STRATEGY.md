# Strategy: mubashirr.com

## State of play

The site is a WordPress 6.9.4 install on the Yummy Bites theme, dormant since May 2023. Five demo posts, no SEO plugin signature, no Open Graph metadata, no analytics, no real content. Treat this as a launch, not a refresh.

## The thesis in one paragraph

Pick a tight niche that does not require ten years of food-blog SEO equity to compete in. Publish one well-built, original, deeply useful post every Saturday. Distribute it intelligently across Pinterest and Instagram (where food traffic actually lives), with secondary fanout to LinkedIn and X. Layer Schema.org Recipe markup and AEO-ready structure from day one. After 12 weeks of consistent publishing, audit which posts gained traction and double down on that direction.

## The niche

Generic food blogs are a saturated graveyard. Three angles that fit you specifically and have addressable search demand:

**Halal cooking with French technique.** Almost nobody owns this intersection. You have the cultural credibility and the geographic placement. Search terms like "halal coq au vin alternative" or "gigot d'agneau halal" have low competition and real intent.

**Healthy weeknight cooking for working parents.** Your stated audience profile (two kids around 8 and 10, busy professional household) is a real ICP. The keyword space is competitive but the specific angle of fast-but-not-junk has room.

**Subcontinental food without the apologetics.** Most western-facing Pakistani and Indian food blogs over-explain or under-deliver. Confident, technique-first writing in the Yousufi register would stand out. Risk: smaller English-speaking audience.

I recommend leading with the first one and bleeding the third in once a month. The fourth Saturday of every month is a heritage recipe.

## The cadence

Wednesday Scout pulls structured data. Thursday Writer drafts; Visual generates images. Friday optional human review window. Saturday 07:00 Paris time Publisher pushes draft to WordPress. Saturday 07:15 you get a Telegram message with preview and approve button. On approve, post flips to published and Distributor starts fanout. Sunday Archivist backs everything up.

If you do not respond to Telegram in two hours, the system auto-publishes. You set that flag.

## Distribution timing per platform

The blog post lands Saturday 07:00. Distributor does not fire all at once.

| Platform | When | Why |
|----------|------|-----|
| Pinterest | Saturday 20:00 then Sunday 11:00 | Pinterest food peaks weekend evenings |
| Instagram carousel | Sunday 11:30 | Sunday brunch scrolling |
| Email newsletter | Tuesday 09:00 | Highest open rates Tue/Thu morning |
| LinkedIn post | Wednesday 08:30 | Professional audience, B2B cadence |
| X thread | Thursday 18:00 | Evening engagement, food gets RTs |
| Facebook | Saturday 19:00 | Local community fb groups, dinner-time scroll |

This is one piece of content, six tailored variants, six different drop times. The Distributor handles each automatically.

## Costs

Hard costs at one post per week:

| Item | Monthly |
|------|---------|
| Anthropic Claude API (writing) | €10 |
| fal.ai Flux Pro (4 images per post) | €1 |
| Edamam Recipe API | €0 |
| Pexels API | €0 |
| Buffer or Publer social scheduling | €5 (or skip and use direct API calls) |
| Backblaze B2 backup | €0.50 |
| Domain and WP hosting | already paid |
| GitHub Actions minutes | €0 (within free tier) |
| **Total** | **~€17** |

Plus your time: ten minutes Saturday morning to approve. Optionally 30 minutes Friday to review the draft.

## Risks I called out, restated

**Legal: scraping.** Not doing it. Scout pulls from APIs that license their data for re-use. Writer generates original prose.

**Quality: AI slop.** The single largest threat. Google's Helpful Content Update penalizes blogs that smell synthetic. Mitigations:
- Long-form (1,400+ words) with real depth, not stuffed filler
- Schema.org Recipe markup (mandatory)
- Author bio with E-E-A-T signals (your real name, your credentials, your story about why you cook)
- First-person voice with specific personal detail in every headnote
- AI images that look like a consistent photographer's portfolio, not stock soup

**Reputational: bad post under your name.** Telegram approval gate. You set the auto-publish timeout. If you are travelling and miss it, system pauses, does not auto-publish.

**Operational: pipeline breaks silently.** Every agent posts pass/fail to a Telegram channel and writes a status file. Archivist's Sunday digest tells you what ran, what failed, what is queued.

**Reputational: a recipe that conflicts with your values.** Hard-coded prompt rules block alcohol, pork, non-halal gelatin, unclear meat sourcing. Scout filters at source. Writer reinforces. You review before publish.

## What success looks like at 12 weeks

Twelve original recipes published. Indexed by Google (Search Console shows them). At least 30 of them indexed in Pinterest with at least 5 saves each. One post in Google's top 10 for at least one long-tail keyword. Email list passes 100 subscribers. You spent on average 15 minutes per week.

If none of those are true at 12 weeks, the niche choice was wrong and we pivot. The pipeline does not change; the prompts and themes do.

## What success looks like at 12 months

Forty to fifty posts. Domain Rating climbing past 15. Pinterest driving 60% of traffic. Email list at 1,000 plus. One viral post (>50k pageviews in a month). At that point, advertising via Mediavine or Raptive becomes viable and the site starts paying for its own automation.
