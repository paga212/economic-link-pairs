#!/usr/bin/env bash
# Weekly paper-trade tick: emit rec (deduped per holding month), score matured ones,
# regenerate the local HTML dashboard, and commit/push the log. Cron: 0 9 * * 1 (Mon 09:00).
set -uo pipefail
cd /home/pierre/projects/economic-link-pairs || exit 1

python3 recommend.py >> paper_run.log 2>&1
python3 score.py     >> paper_run.log 2>&1
python3 dashboard.py >> paper_run.log 2>&1
bash serve.sh

git add paper_log.jsonl
if ! git diff --cached --quiet; then
  git commit -q -m "paper: weekly tick $(date +%Y-%m-%d)"
  git pull --rebase --autostash -q origin main || true
  git push -q origin main || true
fi
