#!/usr/bin/env bash
# Run this once in your Terminal from the project folder.
#   chmod +x setup.sh && ./setup.sh
#
# What it does:
#   1. Resets the partial .git/ that the sandbox left behind.
#   2. Initialises a fresh git repo, commits all scaffolding.
#   3. Pushes to your private GitHub repo.

set -euo pipefail
cd "$(dirname "$0")"

# Clean the stale .git/ from the sandbox attempt.
rm -rf .git

git init -b main
git config user.email "mubashirr@gmail.com"
git config user.name  "Dr Mubashir"

git add -A
git commit -m "initial scaffolding: 6-agent recipe pipeline + strategy docs"

git remote add origin git@github.com:malikmubashir/mubashirr-com-automation.git
git push -u origin main

echo
echo "Repository pushed. Next step: add the GitHub Secrets."
echo "Opening: https://github.com/malikmubashir/mubashirr-com-automation/settings/secrets/actions"
open "https://github.com/malikmubashir/mubashirr-com-automation/settings/secrets/actions" 2>/dev/null || true
