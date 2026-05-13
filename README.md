# mubashirr.com automation

Six agents on GitHub Actions cron, publishing one original recipe to WordPress every Saturday and fanning it across social channels. English at launch. One-tap Telegram approval before publish.

## Read in this order

1. `STRATEGY.md` — the why, the cadence, the costs, the risks I called out
2. `ARCHITECTURE.md` — what each agent does and how they hand off
3. `SEO-AEO-PLAN.md` — concrete site setup before the first post ships
4. `CONTENT-CALENDAR.md` — first 12 weeks of themes
5. `pipeline/` — Python skeleton for each agent
6. `.github/workflows/weekly-pipeline.yml` — the cron orchestration

## Run order on your first day

```
cd pipeline
cp .env.example .env          # fill in API keys
pip install -r requirements.txt
python -m agents.scout        # produces drafts/scout-<date>.json
python -m agents.writer       # produces drafts/post-<date>.md
python -m agents.visual       # produces drafts/images/*.png
python -m agents.publisher --dry-run   # validates without posting
```

Once that works locally, push to GitHub. The workflow runs on its own.

## What you owe before this works

| Thing | Where to get it | Free? |
|-------|-----------------|-------|
| WordPress Application Password | `mubashirr.com/wp-admin/profile.php` | yes |
| Anthropic API key | `console.anthropic.com` | no, ~€10/mo at this cadence |
| fal.ai API key | `fal.ai` | no, ~€1/mo at this cadence |
| Edamam Recipe API key | `developer.edamam.com` | free tier sufficient |
| Pexels API key | `pexels.com/api` | yes |
| Telegram bot token | message `@BotFather` | yes |
| Backblaze B2 bucket | `backblaze.com/b2` | ~€0.50/mo |
| GitHub repo (private) | `github.com` | free |

Total monthly run rate: under €15 assuming one post per week.
