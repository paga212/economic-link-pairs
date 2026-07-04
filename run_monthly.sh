#!/usr/bin/env bash
# Monthly paper-trade tick: emit this month's recommendation, score matured ones,
# and commit/push the out-of-sample log. Cron: 0 9 2 * * (09:00 on the 2nd).
set -uo pipefail
cd /home/pierre/projects/economic-link-pairs || exit 1

python3 recommend.py >> paper_run.log 2>&1
python3 score.py     >> paper_run.log 2>&1

git add paper_log.jsonl
if ! git diff --cached --quiet; then
  git commit -q -m "paper: monthly recommendation $(date +%Y-%m)"
  git pull --rebase --autostash -q origin main || true
  git push -q origin main || true
fi
