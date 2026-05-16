# Where we are — 16 May 2026

## What works end to end

- Repo: github.com/malikmubashir/mubashirr-com-automation (private)
- Six agents in `pipeline/agents/`, workflow at `.github/workflows/weekly-pipeline.yml`
- Each agent commits its output to git so the next picks it up
- **Scout** validated: pulls Edamam recipes, filters halal, writes `drafts/<date>/scout.json`
- **Writer** validated: Claude Sonnet 4.6 produces 1,400+ word original posts in the configured voice. The first sample (`drafts/2026-05-16/post.md`) is high quality
- **Cloudflare bypass** validated: `pipeline/agents/common.py` resolves the WP host directly to the origin IP when `WP_ORIGIN_IP` is set, with TLS validated against the pinned Cloudflare Origin CA roots in `pipeline/certs/`
- GitHub Secrets all in place except Buffer (optional), MySQL/B2 (optional), and **`WP_ORIGIN_IP` (must be added — see below)**

## Architecture pivot — cron-pull on the host (16 May 2026)

The site sits on **Hosting Made Easy** (cPanel reseller, origin IP `210.2.169.195`). Authoritative DNS lives on Cloudflare nameservers (`jason.ns.cloudflare.com`, `sloan.ns.cloudflare.com`) in the host's account, which we don't control. cPanel username is `mubashir`, home at `/home/mubashir/`.

Three blockers stacked against direct push from GH Actions:
1. Going through Cloudflare — Bot Fight Mode challenges Azure egress on TLS fingerprint / IP reputation.
2. Going around Cloudflare to origin — origin firewall silently drops SYNs from Azure egress (verified: GH run id `25956514581` hit 60s connect timeout on `/wp-json/wp/v2/media`).
3. SSH is not enabled on this hosting plan.

**Pivot: host pulls instead of being pushed to.** cPanel Git Version Control clones this repo to the host. A PHP script at `host/cron/mubashirr_pull.php` runs every 10 min via cPanel Cron Jobs, reads the latest committed draft from the local checkout, sideloads images into WP media library, creates the post as draft, sends Telegram with edit/preview links. User publishes manually from WP admin.

What changed in this repo:
- `pipeline/agents/writer.py` now writes `meta.json` alongside `meta.yaml` (cron PHP reads JSON).
- `pipeline/agents/visual.py` skips WP upload when `WP_SKIP_UPLOAD=true` (set in workflow). Images saved locally; the workflow commits the PNGs.
- `.gitignore` no longer excludes `drafts/*/images/*.png`.
- `.github/workflows/weekly-pipeline.yml` — SSH tunnel step removed, Visual env trimmed to fal.ai/Pexels only, Publisher reduced to a stub for `workflow_dispatch`.
- `host/cron/mubashirr_pull.php` — the new PHP processor.
- `host/cron/config.php.example` — config template.
- `host/cron/README.md` — deployment steps for cPanel.

**Action required from user — host-side setup:**
1. cPanel → Git Version Control → clone the repo to `/home/mubashir/repositories/mubashirr-com-automation` (use a GitHub PAT if private).
2. cPanel → File Manager → create `/home/mubashir/cron/`, copy in `config.php` from `config.php.example`, fill in `wp_root`, `wp_host`, and Telegram creds if desired. Chmod 600.
3. Test once manually (see `host/cron/README.md` step 3).
4. cPanel → Cron Jobs → add: `*/10 * * * * /usr/local/bin/php /home/mubashir/repositories/mubashirr-com-automation/host/cron/mubashirr_pull.php >> /home/mubashir/cron/cron.log 2>&1`.

**No GH secrets needed for this path.** `WP_ORIGIN_IP`, `WP_SSH_*` from prior attempts can be deleted from repo secrets — they're no longer referenced.

**Verified locally:** Writer's meta.json output works (backfilled for 2026-05-16 draft). PHP script is syntactically reviewed; full runtime test happens on first cron run.

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
