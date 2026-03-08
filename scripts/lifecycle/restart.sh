#!/bin/bash
# Adjutant full restart script
# Stops everything and starts fresh

set -e

# Resolve ADJ_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/logging.sh"

TIMESTAMP=$(date "+%H:%M:%S %d.%m.%Y")

echo "🔄 Adjutant Restart - ${TIMESTAMP}"

# =========================
# STOP SERVICES
# =========================

echo ""
echo "Stopping services..."
echo ""

# Stop Telegram Listener
if [ -f "${ADJ_DIR}/state/telegram.pid" ] && kill -0 $(cat "${ADJ_DIR}/state/telegram.pid") 2>/dev/null; then
  "${ADJ_DIR}/scripts/messaging/telegram/service.sh" stop
  echo "✓ Telegram listener stopped"
else
  echo "✓ Telegram listener not running"
fi

# Stop OpenCode Web Server
if [ -f "${ADJ_DIR}/state/opencode_web.pid" ] && kill -0 $(cat "${ADJ_DIR}/state/opencode_web.pid") 2>/dev/null; then
  kill $(cat "${ADJ_DIR}/state/opencode_web.pid") 2>/dev/null || true
  rm -f "${ADJ_DIR}/state/opencode_web.pid"
  echo "✓ OpenCode web server stopped"
else
  # Try to find and kill any running opencode serve
  if pgrep -f "opencode serve" > /dev/null 2>&1; then
    pkill -TERM -f "opencode serve" 2>/dev/null || true
    sleep 1
    echo "✓ OpenCode web server stopped"
  else
    echo "✓ OpenCode web server not running"
  fi
fi

echo ""
echo "Waiting for clean shutdown..."
sleep 2

# =========================
# START SERVICES
# =========================

echo ""
echo "Starting services..."
echo ""

# Use startup.sh for the startup logic
"${ADJ_DIR}/scripts/lifecycle/startup.sh"

echo ""
echo "✅ Restart complete"
