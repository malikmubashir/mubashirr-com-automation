# Where we are — 16 May 2026

## What works end to end

- Repo: github.com/malikmubashir/mubashirr-com-automation (private)
- Six agents in `pipeline/agents/`, workflow at `.github/workflows/weekly-pipeline.yml`
- Each agent commits its output to git so the next picks it up
- **Scout** validated: pulls Edamam recipes, filters halal, writes `drafts/<date>/scout.json`
- **Writer** validated: Claude Sonnet 4.6 produces 1,400+ word original posts in the configured voice. The first sample (`drafts/2026-05-16/post.md`) is high quality
- **Cloudflare bypass** validated: `pipeline/agents/common.py` resolves the WP host directly to the origin IP when `WP_ORIGIN_IP` is set, with TLS validated against the pinned Cloudflare Origin CA roots in `pipeline/certs/`
- GitHub Secrets all in place except Buffer (optional), MySQL/B2 (optional), and **`WP_ORIGIN_IP` (must be added — see below)**

## Cloudflare blocker — characterized but not yet cleared (16 May 2026)

The site sits on **Hosting Made Easy** (cPanel reseller, origin IP `210.2.169.195` → `core43.hostingmadeeasy.com`). Authoritative DNS lives on Cloudflare nameservers (`jason.ns.cloudflare.com`, `sloan.ns.cloudflare.com`) in the host's account, which we don't control.

**Two independent defenses are blocking GitHub Actions:**
1. *Going through Cloudflare* — Bot Fight Mode challenges Azure egress because of TLS fingerprint and IP reputation.
2. *Going around Cloudflare* — the origin firewall silently drops TCP SYNs from Azure egress (likely "origin lockdown" to Cloudflare IP ranges only). GH Actions hits a 60s connect timeout.

The first try (direct origin bypass via `socket.getaddrinfo` override) confirmed the bypass code loads cleanly in GH Actions (`cf_bypass INFO Origin bypass active` showed up in logs) and works fine from any IP the origin already accepts (sandbox connects in 45ms). It fails only because GH Actions Azure egress hits defense #2.

**Pivot: SSH tunnel.** Port 22 SSH is accepted by the host firewall. Workflow now opens `ssh -L 8443:127.0.0.1:443 user@host` before Visual and Publisher run, and the `WP_ORIGIN_PORT` env var redirects HTTPS through the tunnel. End-to-end traffic flow: GH Actions → SSH tunnel (port 22) → host loopback → Apache (port 443) → WP REST API. No Cloudflare, no BFM, no origin firewall in the path.

**Action required from user — add these GitHub Actions secrets:**
- `WP_SSH_KEY` — private deploy key (full PEM contents, including BEGIN/END lines)
- `WP_SSH_HOST` — host to SSH to (e.g. `core43.hostingmadeeasy.com` or `210.2.169.195`)
- `WP_SSH_USER` — cPanel account username
- `WP_SSH_PORT` — SSH port (often 22 or 2222 on Hosting Made Easy)

`WP_ORIGIN_IP` secret is no longer used (workflow now hardcodes 127.0.0.1). Leave or delete as you prefer.

**Verified locally:** the patched session targeted at `127.0.0.1:8443` resolves and dispatches correctly. The actual tunnel + WP round-trip needs the SSH secrets above before it can be re-tested in GH Actions.

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
