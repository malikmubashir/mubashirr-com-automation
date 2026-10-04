# Pipeline v2 (October 2026): one job, a stock of drafts, one contract

This supersedes the "six agents on a cron" design in `ARCHITECTURE.md` and the
cron-pull host architecture in `STATUS.md`. Those files are kept for history.

## Why v1 failed

v1 ran scout, writer and visual as three independent GitHub cron entries that
only communicated through git commits. GitHub cron is best effort: the writer
committed at 11:55, 12:16, 12:23 and 13:59 UTC on successive Thursdays against
a 07:00 schedule, and visual at 13:23, 14:10, 14:05. Visual only produced
images when it happened to fire after the writer. On 2026-10-01 it did not,
and in addition the writer had emitted a malformed image brief (`ingredients`
instead of `prompt`) that would have crashed visual anyway. Nothing checked
completeness; the distributor then queued social posts for a URL that did not
exist. There was no buffer, so one failed step meant one missed Saturday.

## Shape

```
GitHub Actions: produce.yml, weekdays 05:15 UTC          Claude daily task (07:00 Paris)
───────────────────────────────────────────────          ────────────────────────────────
python -m pipeline.produce                                GET drafts/index.json
  rebuild drafts/index.json                               for each complete draft not yet
  stock = complete drafts for future Saturdays              on the site, date <= next Saturday:
  if stock >= STOCK_TARGET (2): exit 0                        fetch files, verify sha256 against
  else, for the earliest gap:                                 manifest.json, create WP draft
     scout -> writer -> visual -> validate -> manifest      publish drafts whose date is due
  one atomic commit, or no commit at all                    report: stock, published, problems
```

## The contract: `drafts/<date>/manifest.json`

A draft exists for downstream purposes only if `manifest.json` is present and
every listed file still matches its sha256. `pipeline/validate.py` is the only
writer of manifests and runs these checks first: meta.json fields, four image
briefs with prompt and alt, post.md front matter, word floor, the exact
`## Ingredients` / `## Method` / `## Variations` lines the host mu-plugin
needs, no JSON-LD in the body, schema.json is a Recipe, four decodable images
of sensible size, slug and title unique across all drafts (and, with
`CHECK_LIVE=true`, across the live site).

`drafts/index.json` is regenerated on every run: `stock`, `next_due`,
`complete[]`, `partial[]` (with the first three problems), `legacy[]` (pre-v2
folders that never had a manifest).

## Operating it

Stock full is the normal state; the job then exits in seconds. Red run means
one step failed and nothing was committed; the next weekday retries. Look at
the run's step summary for the stock line.

Manual runs (Actions tab, produce, "Run workflow"):

- backfill a specific Saturday: `draft_date=2026-10-03` (existing scout/writer
  output is kept, only missing steps run)
- regenerate text and images: same, plus `force=true`
- grow the buffer: `stock_target=3`

Local:

```
python -m pipeline.validate --date 2026-10-10            # report
python -m pipeline.validate --date 2026-10-10 --write    # write manifest
python -m pipeline.validate --date 2026-10-10 --verify   # check hashes
DRAFT_DATE=2026-10-10 python -m pipeline.produce
```

## What was removed

`weekly-pipeline.yml` (six cron entries), the publisher stub, the scheduled
distributor. `host/cron/` is dead code since 2026-09-19 and can be deleted
after one clean week. `archive.yml` keeps the Sunday DB backup unchanged.
`distribute.yml` is manual only and refuses to run unless the post URL you
pass returns 200 and the draft has a manifest.

## Alerts worth having

Stock below 1; two consecutive red produce runs; a publish failure in the
daily task; a published URL that does not return 200. Everything else is
noise.
