# Architecture: six agents on a cron

## Design principles

1. Filesystem is the message bus. Each agent reads inputs from disk, writes outputs to disk, hands off through git commits. No agent framework, no orchestrator, no LangChain weight. Just Python scripts and YAML.
2. One agent, one job. Each module is independently runnable, testable, and replaceable.
3. Idempotent runs. Re-running an agent on the same input produces the same output. Failures are safe to retry.
4. Human approval is a real step, not a rubber stamp. The Telegram gate is between Publisher (draft) and the public.
5. Everything is versioned. Posts as Markdown in git. Database dumps in B2 with weekly rotation.

## The agents

### Scout — Wednesday 09:00 Paris

**Inputs**: `config/theme-rotation.yaml` (current week's theme), `state/published-history.json` (avoid repeats).

**What it does**: queries Edamam, TheMealDB, and Open Food Facts for candidate recipes matching this week's theme. Filters out non-halal, repeats, low-quality entries. Pulls Google Trends data on related searches to score SEO potential. Ranks top 5 candidates.

**Outputs**: `drafts/<date>/scout.json` with the top candidate plus 4 alternates, each enriched with ingredient list, nutrition facts, cuisine tags, estimated prep/cook time, and an SEO score.

**Failure mode**: if all APIs are down, falls back to a hand-curated backlog in `config/backlog.yaml`.

### Writer — Thursday 09:00 Paris

**Inputs**: `drafts/<date>/scout.json`, `config/voice-guide.md` (the prose style spec), `config/post-template.md`.

**What it does**: takes the top Scout candidate. Calls Claude Sonnet with a long-form prompt that produces a 1,400–1,800 word post including headnote story, ingredient notes, method, variations, storage, and FAQ. Generates Schema.org Recipe JSON-LD. Generates SEO title, slug, meta description, and 8–12 tags.

**Outputs**: `drafts/<date>/post.md` (with YAML front matter), `drafts/<date>/schema.json`, `drafts/<date>/meta.yaml`.

**Failure mode**: if Claude API errors, writes a clear log and exits non-zero. The next stage will not run on a missing file.

### Visual — Thursday 11:00 Paris

**Inputs**: `drafts/<date>/post.md`, `drafts/<date>/meta.yaml`.

**What it does**: extracts the four image briefs from the post (hero, ingredients flat-lay, mid-process, plated). Calls fal.ai Flux Pro with a brand-consistent style prompt for each. Saves to `drafts/<date>/images/`. Generates alt text for each image (accessibility plus SEO). Uploads to WordPress media library via REST API; records returned media IDs in `meta.yaml`.

**Outputs**: 4 PNG files, updated `meta.yaml` with media IDs.

**Failure mode**: if fal.ai fails, falls back to Pexels API search using post tags. Logs the fallback.

### Publisher — Saturday 07:00 Paris

**Inputs**: `drafts/<date>/post.md`, `drafts/<date>/meta.yaml`, `drafts/<date>/schema.json`.

**What it does**: converts Markdown to WordPress block format (Gutenberg). Creates a draft post via WordPress REST API with title, slug, content, featured image, categories, tags, meta description, and Recipe schema. Sends a Telegram message with preview link, approve button, reject button. On approve, flips post status from draft to publish. On reject, deletes the draft and notifies. On timeout (configurable, default 2 hours), auto-publishes if `AUTO_PUBLISH_ON_TIMEOUT=true` in config.

**Outputs**: post live on mubashirr.com, `state/published-history.json` updated, Telegram confirmation.

**Failure mode**: if WP API errors, retries 3 times with backoff. If still failing, pages you via Telegram with the error.

### Distributor — fires per platform on schedule

**Inputs**: published post URL, `meta.yaml`, generated images.

**What it does**: composes platform-specific variants and schedules them via Buffer API (or directly via each platform's API if you prefer to skip Buffer).

| Variant | Content |
|---------|---------|
| Pinterest pin | 1000x1500 vertical with text overlay of recipe title, scheduled Saturday 20:00 and Sunday 11:00 |
| Instagram carousel | 4 squares (hero, ingredients overhead, step, plated final) with caption and 12 hashtags, scheduled Sunday 11:30 |
| Email newsletter | HTML email via Buttondown or Beehiiv, scheduled Tuesday 09:00 |
| LinkedIn | Long-form post angled on the cultural/technique story, scheduled Wednesday 08:30 |
| X thread | 5 tweets: hook, technique, 2 ingredient tips, link, scheduled Thursday 18:00 |
| Facebook | Standard share with hero image, scheduled Saturday 19:00 |

**Outputs**: scheduling confirmations, `state/distribution-<date>.json` log.

**Failure mode**: each platform is independent. A failure on X does not block Pinterest.

### Archivist — Sunday 22:00 Paris

**Inputs**: WordPress MySQL database, wp-content directory, this repo.

**What it does**: runs `mysqldump` on the WP database. Encrypts with `age`. Uploads to Backblaze B2 with date-stamped filename. Keeps last 12 weekly backups, last 12 monthly, last 5 yearly. Commits this week's drafts, schemas, generated images, and prompts to a private git repo. Generates a Markdown weekly digest of what was published, what is queued, error summary.

**Outputs**: encrypted DB backup in B2, git commit, weekly digest sent to your email.

**Failure mode**: if mysqldump fails, alerts via Telegram. If B2 upload fails, retries; falls back to local copy on the runner with alert.

## Sequence diagram

```
Wed 09:00  Scout      → drafts/<date>/scout.json
Thu 09:00  Writer     → drafts/<date>/post.md + schema + meta
Thu 11:00  Visual     → drafts/<date>/images/*.png + WP media uploads
Fri        (you can review the draft in the repo; optional)
Sat 07:00  Publisher  → WP draft + Telegram message to you
Sat ~07:01 you tap Approve in Telegram
Sat 07:02  Publisher  → flips draft to published
Sat 07:05  Distributor → schedules 6 social variants over the next 5 days
Sun 22:00  Archivist  → DB backup + git commit + weekly digest email
```

## Where state lives

```
/                                  this repo
├── config/                        prompts, voice guide, theme rotation, backlog
├── drafts/<YYYY-MM-DD>/           weekly working directory
│   ├── scout.json
│   ├── post.md
│   ├── schema.json
│   ├── meta.yaml
│   └── images/
├── state/                         persistent state across runs
│   ├── published-history.json     to avoid repeats
│   └── distribution-<date>.json   per-week dist log
├── pipeline/agents/               the six Python modules
└── .github/workflows/             GitHub Actions cron files
```

## What you can swap later

Each agent is one Python file. Costs or quality issues with any single component (e.g., Flux not delivering the brand look) means swapping one module, not rebuilding. The contracts between agents are JSON files on disk.
