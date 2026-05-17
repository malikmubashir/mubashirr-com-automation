# Where we are — 16 May 2026

## What works end to end

- Repo: github.com/malikmubashir/mubashirr-com-automation (private)
- Six agents in `pipeline/agents/`, workflow at `.github/workflows/weekly-pipeline.yml`
- Each agent commits its output to git so the next picks it up
- **Scout** validated: pulls Edamam recipes, filters halal, writes `drafts/<date>/scout.json`
- **Writer** validated: Claude Sonnet 4.6 produces 1,400+ word original posts in the configured voice. The first sample (`drafts/2026-05-16/post.md`) is high quality
- **Cloudflare bypass** validated: `pipeline/agents/common.py` resolves the WP host directly to the origin IP when `WP_ORIGIN_IP` is set, with TLS validated against the pinned Cloudflare Origin CA roots in `pipeline/certs/`
- GitHub Secrets all in place except Buffer (optional), MySQL/B2 (optional), and **`WP_ORIGIN_IP` (must be added — see below)**

## Architecture — cron-pull on the host (working as of 17 May 2026)

The site sits on **Hosting Made Easy** (cPanel reseller, origin IP `210.2.169.195`, cPanel user `mubashir`). Authoritative DNS lives on Cloudflare nameservers (`jason.ns.cloudflare.com`, `sloan.ns.cloudflare.com`) in the host's account, which we don't control.

### Why cron-pull

Four independent blockers killed every attempt to push from GH Actions:
1. Going through Cloudflare — Bot Fight Mode challenges Azure egress on TLS fingerprint / IP reputation.
2. Going around Cloudflare to origin — origin firewall silently drops SYNs from Azure egress (verified: GH run `25956514581` hit 60s connect timeout on `/wp-json/wp/v2/media`).
3. SSH access is not on this plan and the host won't enable it (Nexus Technologies reply 17 May 2026 — VPS upgrade required).
4. Even via cPanel Git Version Control, the host disables `exec/shell_exec/proc_open/system` in PHP, so `git pull` isn't callable. AND the host's outbound firewall blocks `api.github.com` while permitting `raw.githubusercontent.com`.

### The shape that works

```
GitHub repo (public)                  cPanel host (mubashirr.com)
─────────────────                     ──────────────────────────
Scout    (Wed)  → commits scout.json   ┐
Writer   (Thu)  → commits post.md +    │   every 10 min cron:
                  meta.json +          │     /usr/local/bin/php
                  schema.json          ├──► /home/mubashir/repositories/.../host/cron/mubashirr_pull.php
Visual   (Thu)  → commits images PNGs  │       │
                                       │       │ bootstrap: file_get_contents
                                       │       │  https://raw.githubusercontent.com/.../host/cron/mubashirr_pull.php
                                       │       │  → /tmp/mubashirr_pull_latest.php
                                       │       │  require it
                                       │       ▼
                                       │     main script:
                                       │       probes last 60 days of Saturdays for drafts/<date>/meta.json
                                       │       fetches meta.json, post.md, schema.json, images via raw URLs
                                       │       wp_insert_post(status=draft) + media_handle_sideload x4
                                       │       set_post_thumbnail(hero)
                                       │       Telegram notify (if configured)
                                       │       state.json marks slug processed
                                       │
                                       │   You: review in WP admin, click Publish
```

### Key implementation details

- **Repo is public.** Private+cPanel-Git failed because cPanel rejects URLs containing credentials (`https://user:pass@github.com/`) and the host blocks SSH. Public repo skips the auth problem entirely.
- **Bootstrap pattern.** The PHP file at the cron's target path is a 30-line bootstrap that fetches the real script from `raw.githubusercontent.com` and runs it. Updates to the script land on the host on the next cron tick — no manual host-side file syncing.
- **No api.github.com.** The host blocks it. We probe for the latest draft by iterating Saturday dates (last 60 days) and HEAD-checking `drafts/<date>/meta.json` via raw URLs.
- **No `git pull` on host.** Everything fetched via `file_get_contents` over HTTPS to `raw.githubusercontent.com`.
- **Wait-for-images guard.** Cron exits cleanly if any expected image PNG isn't yet on remote — prevents creating a post without images and locking out future image attachments.
- **State file at** `/home/mubashir/cron/state.json` tracks processed slugs. Idempotent.

### Verified end-to-end (17 May 2026, 13:08 UTC)

First successful run: draft post ID 80 created from `drafts/2026-05-16/` (Vadouvan-spiced leg of lamb). 4 images sideloaded (media_ids 76-79), featured image set, state.json updated.

### Files of interest

- `host/cron/mubashirr_pull.php` — the cron processor (canonical source; raw-URL-fetched by the bootstrap)
- `host/cron/config.php.example` — config template
- `host/cron/README.md` — cPanel setup walkthrough
- `pipeline/agents/common.py` — `DRAFT_DATE` env var support for backfill runs
- `pipeline/agents/visual.py` — `WP_SKIP_UPLOAD=true` mode (the only mode in current workflow)
- `.github/workflows/weekly-pipeline.yml` — workflow_dispatch accepts `draft_date` input

### Long-term housekeeping

- The host's restrictions (no SSH, exec disabled, api.github.com blocked, etc.) make it a poor fit. A €5-10/mo VPS (Hetzner CX22, Scaleway DEV1) would let you own the stack and remove most of this complexity. Not urgent but budget for it after launch.
- Public repo means architecture docs and content calendar are world-readable. If that becomes a concern, the alternative is migrating to a host where private clone over SSH works.

## Remaining blocker

### fal.ai balance not yet funded

User reached the billing-address page but did not complete the $12 charge (10 USD + 2 USD VAT). Top-up flow requires:
1. Save billing address (Global Apex, France, VAT FR89941666067)
2. Confirm $12 via Stripe-style payment form
3. Balance shows $10 in fal.ai dashboard
4. API stops returning "Exhausted balance"

Until balance is loaded, Visual falls back to Pexels.

## What to test next once `WP_ORIGIN_IP` secret is set and fal.ai is funded

1. Re-run Visual via workflow_dispatch. Expect 4 fal.ai images uploaded to WordPress media library, `meta.yaml` updated with media IDs.
2. Test Publisher with `--dry-run` style flag (the agent has the same code path; it creates a WordPress draft post).
3. Validate Telegram approval gate: Publisher should send a message to chat 813119984 with Approve/Reject buttons.
4. Test the Schema.org Recipe markup in Google's Rich Results Test.

## Open content/strategy items (lower priority)

- Seed keywords in `pipeline/config/theme-rotation.yaml` need tightening. "halal french cooking" returns mostly Pakistani lamb dishes, not French. Better seeds: `gigot d'agneau`, `verjus reduction`, `tagine recipe`, `lamb shoulder slow roast`.
- First draft post (Vadouvan-Spiced Leg of Lamb) is a 4-hour, 8-person dinner-party recipe. Too ambitious for steady-state. Fine for launch week.
- Author bio at `/about` not yet created on the live WP site. Needed for E-E-A-T.
- RankMath SEO plugin not yet installed. Schema.org Recipe markup currently emitted by Writer only; once RankMath is installed, disable its recipe schema to avoid duplicates.

## Quick re-entry commands

```bash
cd ~/Documents/Claude/Projects/Mubashirr.Com
git pull --rebase

# Verify the bot has been committing while away
git log --oneline | head -20
```

To re-trigger a specific agent manually:
`Actions → weekly-pipeline → Run workflow → enter agent name`
