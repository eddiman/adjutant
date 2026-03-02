#!/bin/bash
# Adjutant emergency kill switch
# Nuclear shutdown of all systems

set -e

# Resolve ADJ_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"
source "${COMMON}/logging.sh"

LOGFILE="${ADJ_DIR}/journal/$(date +%Y-%m-%d).md"
TIMESTAMP=$(date "+%H:%M:%S %d.%m.%Y")

echo "🚨 EMERGENCY KILL SWITCH ACTIVATED - ${TIMESTAMP}"
echo ""

# =========================
# PRE-KILL NOTIFICATION
# =========================

echo "Sending pre-kill notification to Telegram..."
"${ADJ_DIR}/scripts/messaging/telegram/notify.sh" "🚨 EMERGENCY KILL SWITCH ACTIVATED

Terminating:
- All opencode processes
- Telegram listener  
- News briefing jobs
- Cron scheduler

System will be locked until recovery." 2>/dev/null || true

echo ""

# =========================
# CREATE KILLED LOCKFILE
# =========================

set_killed
echo "✓ KILLED lockfile created"

# =========================
# TERMINATE OPENCODE PROCESSES
# =========================

echo "Terminating OpenCode processes..."

# Try graceful shutdown first
pkill -TERM -f "opencode" 2>/dev/null || true
sleep 2

# Force kill any remaining
pkill -KILL -f "opencode" 2>/dev/null || true

# Clean up PID file
rm -f "${ADJ_DIR}/state/opencode_web.pid"

echo "✓ OpenCode processes terminated"

# =========================
# TERMINATE TELEGRAM LISTENER
# =========================

echo "Terminating Telegram listener..."

# Kill via PID file
if [ -f "${ADJ_DIR}/state/telegram.pid" ]; then
  kill -TERM $(cat "${ADJ_DIR}/state/telegram.pid") 2>/dev/null || true
  sleep 1
  kill -KILL $(cat "${ADJ_DIR}/state/telegram.pid") 2>/dev/null || true
  rm -f "${ADJ_DIR}/state/telegram.pid"
fi

# Kill via listener.lock PID (the actual listener process)
if [ -f "${ADJ_DIR}/state/listener.lock/pid" ]; then
  kill -TERM $(cat "${ADJ_DIR}/state/listener.lock/pid") 2>/dev/null || true
  sleep 1
  kill -KILL $(cat "${ADJ_DIR}/state/listener.lock/pid") 2>/dev/null || true
fi
rm -rf "${ADJ_DIR}/state/listener.lock"

# Kill any orphaned listener processes (matches both old and new paths)
pkill -TERM -f "telegram_listener.sh" 2>/dev/null || true
pkill -TERM -f "messaging/telegram/listener.sh" 2>/dev/null || true

echo "✓ Telegram listener terminated"

# =========================
# TERMINATE NEWS JOBS
# =========================

echo "Terminating news jobs..."

pkill -TERM -f "news_briefing.sh" 2>/dev/null || true
pkill -TERM -f "news/briefing.sh" 2>/dev/null || true
pkill -TERM -f "fetch_news.sh" 2>/dev/null || true
pkill -TERM -f "news/fetch.sh" 2>/dev/null || true
pkill -TERM -f "analyze_news.sh" 2>/dev/null || true
pkill -TERM -f "news/analyze.sh" 2>/dev/null || true

echo "✓ News jobs terminated"

# =========================
# DISABLE CRONTAB
# =========================

echo "Disabling crontab..."

# Backup current crontab
crontab -l > "${ADJ_DIR}/state/crontab.backup" 2>/dev/null || true

# Remove crontab
crontab -r 2>/dev/null || true

echo "✓ Crontab disabled (backed up to state/crontab.backup)"

# =========================
# LOG THE EVENT
# =========================

echo ""  >> "${LOGFILE}"
echo "[${TIMESTAMP}] 🚨 EMERGENCY KILL SWITCH ACTIVATED" >> "${LOGFILE}"
echo "All processes terminated, cron disabled, system locked." >> "${LOGFILE}"
adj_log "emergency" "EMERGENCY KILL SWITCH ACTIVATED — all processes terminated, cron disabled"

echo "✓ Event logged to journal"

# =========================
# FINAL NOTIFICATION
# =========================

echo "Sending final notification..."

"${ADJ_DIR}/scripts/messaging/telegram/notify.sh" "✅ System locked down.

To recover:
  adjutant start
  (or: ${ADJ_DIR}/scripts/lifecycle/startup.sh)

KILLED lockfile created at:
  ${ADJ_DIR}/KILLED" 2>/dev/null || true

# =========================
# COMPLETE
# =========================

echo ""
echo "========================================="
echo "✅ Emergency shutdown complete"
echo "========================================="
echo ""
echo "System is LOCKED."
echo "Run startup to recover:"
echo "  adjutant start"
echo "  (or: ${ADJ_DIR}/scripts/lifecycle/startup.sh)"
echo ""
