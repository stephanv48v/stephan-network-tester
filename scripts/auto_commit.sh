#!/usr/bin/env bash
# Automated Git Commit & Push Helper for /opt/stephan-network-tester
set -e
cd /opt/stephan-network-tester
MSG="${1:-chore: automated appliance configuration & codebase sync}"
git add -A
if ! git diff --cached --quiet; then
    git commit -m "$MSG"
    git push origin main || true
fi
