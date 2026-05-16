# Host-side cron-pull deployment

This directory contains the PHP script that runs on the WordPress host and pulls new content from this repo. Architecture rationale: GitHub Actions cannot reach the origin (firewall drops Azure egress), SSH isn't available on this hosting plan, so the host pulls instead of being pushed to.

## What runs where

```
GitHub Actions                          cPanel host (mubashirr.com)
─────────────────                       ──────────────────────────
Scout    (Wed)  → commits scout.json    ─┐
Writer   (Thu)  → commits post.md +     │   git pull every 10 min
                  meta.json +           │       │
                  schema.json           ├──────►│
Visual   (Thu)  → commits images PNGs   │       ▼
                                        │   /home/mubashir/cron/mubashirr_pull.php
                                        │     ├─ sideloads images into WP media
                                        │     ├─ wp_insert_post(...status=draft)
                                        │     ├─ sets featured image
                                        │     └─ Telegram: "post ready, review at /wp-admin/..."
                                        │
                                        │   You: review and publish from WP admin
```

## One-time setup

### 1. Clone the repo on the host via cPanel

cPanel home → **Files → Git Version Control** → **Create**

| Field | Value |
| --- | --- |
| Clone URL | `https://github.com/malikmubashir/mubashirr-com-automation.git` |
| Repository path | `/home/mubashir/repositories/mubashirr-com-automation` |
| Repository name | `mubashirr-com-automation` |

If the repo is private, cPanel will prompt for credentials. Use a GitHub Personal Access Token with `repo` scope as the password (username = your GitHub login). Generate the PAT at https://github.com/settings/tokens with **classic** type, `repo` scope, 1-year expiry.

After clone, verify:
```
ls /home/mubashir/repositories/mubashirr-com-automation/drafts/
```

### 2. Create the config file (outside the repo)

cPanel → **Files → File Manager** → navigate to `/home/mubashir/`. Create a folder `cron`. In `/home/mubashir/cron/`, create a file `config.php` and paste the contents of `host/cron/config.php.example` from this repo, then edit the values.

Critical: set permissions to 600 so it isn't world-readable:
- File Manager → right-click `config.php` → Change Permissions → set to `0600`

### 3. Test the script manually before scheduling

cPanel → **Advanced → Terminal** (if available). Otherwise, use cPanel cron with a "run once now" schedule (every minute, then disable after one run).

```
/usr/local/bin/php /home/mubashir/repositories/mubashirr-com-automation/host/cron/mubashirr_pull.php
```

Watch `/home/mubashir/cron/cron.log`. First run should:
1. `git sync (code=0)` — repo synced
2. `latest draft: 2026-05-16` — found the draft
3. `wp loaded; acting as user_id=N (mubashir)` — WP bootstrap succeeded
4. `sideloaded hero -> media_id=...` ×4 — images uploaded
5. `created draft post_id=...` — post created
6. `set featured image media_id=...` — hero image attached
7. `telegram HTTP=200 ...` — notification sent (if configured)
8. `done. processed_count=1`

If you see any FATAL or WARN, read the message — the script tries to be specific about what's wrong.

### 4. Schedule the cron

cPanel → **Advanced → Cron Jobs** → **Add New Cron Job**

| Field | Value |
| --- | --- |
| Common Settings | Once every 10 minutes |
| Minute | `*/10` |
| Hour | `*` |
| Day | `*` |
| Month | `*` |
| Weekday | `*` |
| Command | `/usr/local/bin/php /home/mubashir/repositories/mubashirr-com-automation/host/cron/mubashirr_pull.php >> /home/mubashir/cron/cron.log 2>&1` |

Click **Add New Cron Job**.

### 5. Operational notes

The script is idempotent — it tracks processed slugs in `/home/mubashir/cron/state.json`. You can safely re-run it; it'll skip work it already did.

To re-process a draft (e.g. after you edited images), remove the slug from `state.json` and re-run.

To pause cron without deleting the job, edit it in cPanel and change Minute to a far-future value, then restore when ready.

## Telegram setup (optional but recommended)

If you don't already have a bot:

1. Open Telegram, search for `@BotFather`, start a chat, run `/newbot`.
2. Pick a name and username (must end in `bot`). BotFather replies with a token like `123456:ABC-DEF...`.
3. Start a chat with your new bot (search its username, send `/start`).
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` — find your `chat.id` in the JSON response.
5. Paste token + chat_id into `/home/mubashir/cron/config.php`.

## Updating the script

The script lives in this repo. To update:

```
cd /home/mubashir/repositories/mubashirr-com-automation
git pull --ff-only
```

The cron will do this automatically each run, but you can force a sync any time.

## Reverting / disabling

To stop cron processing without removing anything:

1. cPanel → Cron Jobs → delete or pause the job entry.
2. To re-enable: re-add with the same command.

To uninstall completely:

1. Delete the cron job.
2. `rm -rf /home/mubashir/cron/` (logs + state + config).
3. cPanel → Git Version Control → delete the repo entry (keeps files; remove `/home/mubashir/repositories/mubashirr-com-automation` manually if you want).

No changes to WordPress itself — uninstalling leaves WP exactly as it was.
