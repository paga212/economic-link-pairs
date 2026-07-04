#!/usr/bin/env bash
# Idempotent, self-healing local dashboard server. Serves ONLY the site/ dir (so repo
# files and secrets are never exposed) on 0.0.0.0:8787. Safe to call repeatedly — starts
# the server only if it isn't already running. Wired to @reboot cron + the weekly run.
PORT=8787
DIR=/home/pierre/projects/economic-link-pairs/site
mkdir -p "$DIR"
if pgrep -f "http.server $PORT" >/dev/null; then exit 0; fi
setsid nohup python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$DIR" \
  >> /home/pierre/projects/economic-link-pairs/paper_run.log 2>&1 &
