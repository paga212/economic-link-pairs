#!/usr/bin/env bash
# Daily paper-trade tick: run the dynamic tracker, regenerate the dashboard, keep the local
# server up, and commit/push the OOS state. Cron: 0 22 * * 1-5 (weekday evenings after close).
set -uo pipefail
cd /home/pierre/projects/economic-link-pairs || exit 1

python3 track.py     >> paper_run.log 2>&1
python3 catalyst.py  >> paper_run.log 2>&1   # News/Catalyst ensemble -> catalyst.json (fails soft)
python3 risk.py      >> paper_run.log 2>&1   # Risk/Borrow facts -> risk.json (fails soft)
python3 digest.py    >> paper_run.log 2>&1   # Fable-5 digest; consumes catalyst.json + risk.json
python3 dashboard.py >> paper_run.log 2>&1
bash serve.sh

git add paper_state.json paper_start.txt
if ! git diff --cached --quiet; then
  git commit -q -m "paper: daily tick $(date +%Y-%m-%d)"
  git pull --rebase --autostash -q origin main || true
  git push -q origin main || true
fi
