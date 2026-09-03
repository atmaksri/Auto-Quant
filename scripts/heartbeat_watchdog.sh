#!/usr/bin/env bash
# heartbeat_watchdog.sh — restart an eth1 bot when systemd says active but its
# log heartbeat is stale (covers silent wedges: process alive, loop dead).
#
# NOTE on timezones: freqtrade logs in SYSTEM LOCAL time (here PDT), so plain
# `date` is the correct clock to compare against. Do NOT compare with `date -u`.
#
# Usage: heartbeat_watchdog.sh [threshold_minutes]   (default 5)
# Safe to run by hand any time — it only restarts genuinely stale services.
set -u

THRESHOLD_MIN="${1:-5}"
BASE=/home/atmaks/repos/Auto-Quant
LOG="$BASE/user_data/logs/heartbeat-watchdog.log"

bot_log() { # $1 = service -> prints "logfile|telegramconfig"
  case "$1" in
    eth1-paper.service)   echo "$BASE/user_data/logs/eth1-dryrun.log|$BASE/user_data/telegram_config.json" ;;
    eth1-rebound.service) echo "$BASE/user_data/logs/eth1-dryrun-rebound.log|$BASE/user_data/telegram_rebound.json" ;;
  esac
}

notify() { # $1 = telegram.json, $2 = message (best-effort, never fails the run)
  local tok chat
  tok=$(python3 -c "import json;print(json.load(open('$1'))['telegram']['token'])" 2>/dev/null) || return 0
  chat=$(python3 -c "import json;print(json.load(open('$1'))['telegram']['chat_id'])" 2>/dev/null) || return 0
  curl -s --max-time 10 -o /dev/null \
    --data-urlencode "chat_id=$chat" --data-urlencode "text=$2" \
    "https://api.telegram.org/bot$tok/sendMessage" || true
}

now=$(date +%s)
for svc in eth1-paper.service eth1-rebound.service; do
  IFS='|' read -r log tg <<< "$(bot_log "$svc")"
  state=$(systemctl --user is-active "$svc" 2>/dev/null || echo unknown)
  if [ "$state" != active ]; then
    echo "$(date '+%F %T %Z') $svc state=$state, skip" >>"$LOG"
    continue
  fi
  # Grace period after (re)start: startup takes ~2 min before first heartbeat.
  started=$(systemctl --user show -p ActiveEnterTimestamp "$svc" | cut -d= -f2)
  started_s=$(date -d "$started" +%s 2>/dev/null || echo 0)
  if [ $(( now - started_s )) -lt 360 ]; then
    echo "$(date '+%F %T %Z') $svc up $(( (now - started_s) / 60 ))m < grace 6m, skip" >>"$LOG"
    continue
  fi
  last=$(grep heartbeat "$log" 2>/dev/null | tail -1 | cut -c1-19)
  last_s=$(date -d "$last" +%s 2>/dev/null || echo 0)
  age_min=$(( (now - last_s) / 60 ))
  if [ "$age_min" -ge "$THRESHOLD_MIN" ]; then
    echo "$(date '+%F %T %Z') $svc STALE heartbeat ${age_min}m (last $last), restarting" >>"$LOG"
    notify "$tg" "⚠️ $svc heartbeat stale ${age_min} min — restarting the bot."
    systemctl --user restart "$svc"
  else
    echo "$(date '+%F %T %Z') $svc ok (heartbeat ${age_min}m ago)" >>"$LOG"
  fi
done
