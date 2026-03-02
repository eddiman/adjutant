#!/bin/bash
# Adjutant unified startup script
# Handles both emergency recovery and normal startup

set -e

# Resolve ADJ_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"
source "${COMMON}/logging.sh"

TIMESTAMP=$(date "+%H:%M:%S %d.%m.%Y")
LOGFILE="${ADJ_DIR}/journal/$(date +%Y-%m-%d).md"

echo "🚀 Adjutant Startup - ${TIMESTAMP}"
echo ""

# =========================
# MODE DETECTION
# =========================

RECOVERY_MODE=false
if is_killed; then
  RECOVERY_MODE=true
  echo "⚠️  KILLED lockfile detected - entering RECOVERY MODE"
  echo ""
fi

# =========================
# RECOVERY MODE
# =========================

if [ "$RECOVERY_MODE" = true ]; then
  echo "This will:"
  echo "  - Remove KILLED lockfile"
  echo "  - Restore crontab from backup"
  echo "  - Start telegram listener"
  echo "  - Start OpenCode web server"
  echo "  - Send status to Telegram"
  echo ""
  read -p "Proceed with recovery? (y/N): " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
  fi
  
  # Remove KILLED
  clear_killed
  echo "✓ KILLED lockfile removed"
  
  # Restore crontab
  if [ -f "${ADJ_DIR}/state/crontab.backup" ]; then
    crontab "${ADJ_DIR}/state/crontab.backup"
    echo "✓ Crontab restored"
  else
    echo "⚠ No crontab backup found"
  fi
  
  # Log recovery
  adj_log "startup" "System recovered from emergency kill switch"
  echo "[${TIMESTAMP}] 🔓 System recovered from emergency kill switch" >> "${LOGFILE}"
fi

# =========================
# START SERVICES
# =========================

echo ""
echo "Starting services..."
echo ""

# 1. Telegram Listener — delegate detection to service.sh (checks listener.lock/pid,
#    telegram.pid, and pgrep in that order to avoid duplicate launches).
_listener_status="$(bash "${ADJ_DIR}/scripts/messaging/telegram/service.sh" status 2>/dev/null || echo "Stopped")"
if echo "${_listener_status}" | grep -q "^Running"; then
  echo "✓ Telegram listener already ${_listener_status}"
else
  _start_output="$(bash "${ADJ_DIR}/scripts/messaging/telegram/service.sh" start 2>&1)"
  if echo "${_start_output}" | grep -q "^Started\|^Already running"; then
    echo "✓ Telegram listener ${_start_output}"
  else
    echo "⚠ Telegram listener: ${_start_output}"
  fi
fi

# 2. OpenCode Web Server
# Kill orphaned instances before starting — after a reboot, the PID file is gone
# but stale processes may still be running from the previous session.
_owned_web_pid=""
[ -f "${ADJ_DIR}/state/opencode_web.pid" ] && _owned_web_pid="$(cat "${ADJ_DIR}/state/opencode_web.pid" 2>/dev/null | tr -d '[:space:]')"
_running_web_pid="$(pgrep -f "opencode web" 2>/dev/null | head -1)"

if [ -n "${_running_web_pid}" ]; then
  if [ -n "${_owned_web_pid}" ] && [ "${_running_web_pid}" = "${_owned_web_pid}" ] && kill -0 "${_owned_web_pid}" 2>/dev/null; then
    echo "✓ OpenCode web server already running (PID ${_owned_web_pid})"
  else
    # Orphan — kill all instances and start fresh
    echo "  Killing orphaned opencode web process(es)..."
    pkill -TERM -f "opencode web" 2>/dev/null || true
    sleep 2
    pkill -KILL -f "opencode web" 2>/dev/null || true
    rm -f "${ADJ_DIR}/state/opencode_web.pid"
    echo "  Starting OpenCode web server..."
    nohup opencode web --mdns > "${ADJ_DIR}/state/opencode_web.log" 2>&1 &
    echo $! > "${ADJ_DIR}/state/opencode_web.pid"
    sleep 2
    if pgrep -f "opencode web" > /dev/null 2>&1; then
      echo "✓ OpenCode web server started (PID $(cat "${ADJ_DIR}/state/opencode_web.pid"))"
    else
      echo "⚠ OpenCode web server failed to start (check ${ADJ_DIR}/state/opencode_web.log)"
    fi
  fi
else
  echo "  Starting OpenCode web server..."
  nohup opencode web --mdns > "${ADJ_DIR}/state/opencode_web.log" 2>&1 &
  echo $! > "${ADJ_DIR}/state/opencode_web.pid"
  sleep 2
  if pgrep -f "opencode web" > /dev/null 2>&1; then
    echo "✓ OpenCode web server started (PID $(cat "${ADJ_DIR}/state/opencode_web.pid"))"
  else
    echo "⚠ OpenCode web server failed to start (check ${ADJ_DIR}/state/opencode_web.log)"
  fi
fi

# 3. Verify Crontab
CRON_CHECK=$(crontab -l 2>/dev/null | grep -c ".adjutant" || echo "0")
if [ "$CRON_CHECK" -gt 0 ]; then
  echo "✓ Crontab configured ($CRON_CHECK job(s))"
else
  echo "⚠ No crontab found"
  echo ""
  read -p "Install news briefing cron job? (y/N): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    (crontab -l 2>/dev/null; echo "0 8 * * 1-5 ${ADJ_DIR}/scripts/news/briefing.sh >> ${ADJ_DIR}/state/news_briefing.log 2>&1") | crontab -
    echo "✓ Crontab installed"
  fi
fi

# =========================
# GATHER STATUS
# =========================

echo ""
echo "Gathering status..."

STATUS_OUTPUT=$("${ADJ_DIR}/scripts/observability/status.sh" 2>/dev/null || echo "Status unavailable")

# =========================
# SEND NOTIFICATION
# =========================

echo ""
echo "Sending Telegram notification..."

if [ "$RECOVERY_MODE" = true ]; then
  NOTIFICATION="🔓 Adjutant Recovered & Online

Recovery complete at ${TIMESTAMP}

${STATUS_OUTPUT}

System is operational.
Send /pause to pause, or /status for updates."
else
  NOTIFICATION="🚀 Adjutant Online

Started at ${TIMESTAMP}

${STATUS_OUTPUT}

System is operational.
Send /pause to pause, or /status for updates."
fi

"${ADJ_DIR}/scripts/messaging/telegram/notify.sh" "$NOTIFICATION" 2>/dev/null && echo "✓ Telegram notification sent" || echo "⚠ Failed to send Telegram notification"

# =========================
# COMPLETE
# =========================

echo ""
echo "========================================="
echo "✅ Startup complete"
echo "========================================="
echo ""
echo "Current status:"
echo "${STATUS_OUTPUT}"
echo ""

if is_paused; then
  echo "⚠️  System is PAUSED"
  echo "   Remove with: adjutant resume"
  echo "   Or send /resume via Telegram"
fi

echo ""
echo "Logs: ${LOGFILE}"
