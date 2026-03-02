#!/bin/bash
# scripts/messaging/telegram/service.sh — start/stop/restart the Telegram listener

# Resolve ADJ_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"
source "${COMMON}/logging.sh"

PIDFILE="${ADJ_DIR}/state/telegram.pid"
LOCKDIR="${ADJ_DIR}/state/listener.lock"
LOCKPID="${LOCKDIR}/pid"
SCRIPT="${ADJ_DIR}/scripts/messaging/telegram/listener.sh"
LOGFILE="${ADJ_DIR}/state/telegram_listener.log"

# --- Unified listener detection ---
# Returns 0 if a listener is alive, sets _LISTENER_PID.
# Priority: listener.lock/pid (authoritative, written by the listener itself),
#           then telegram.pid (written by this launcher),
#           then pgrep as last resort (catches orphans).
_find_listener_pid() {
  _LISTENER_PID=""

  # 1. listener.lock/pid — the listener writes its own PID here
  if [ -d "${LOCKDIR}" ] && [ -f "${LOCKPID}" ]; then
    local lock_pid
    lock_pid="$(cat "${LOCKPID}" 2>/dev/null | tr -d '[:space:]')"
    if [ -n "${lock_pid}" ] && kill -0 "${lock_pid}" 2>/dev/null; then
      _LISTENER_PID="${lock_pid}"
      return 0
    fi
  fi

  # 2. telegram.pid — the nohup wrapper PID we recorded at launch
  if [ -f "${PIDFILE}" ]; then
    local file_pid
    file_pid="$(cat "${PIDFILE}" 2>/dev/null | tr -d '[:space:]')"
    if [ -n "${file_pid}" ] && kill -0 "${file_pid}" 2>/dev/null; then
      _LISTENER_PID="${file_pid}"
      return 0
    fi
  fi

  # 3. pgrep — catch orphans that lost both tracking files
  local pg_pid
  pg_pid="$(pgrep -f "messaging/telegram/listener\\.sh" 2>/dev/null | head -1)"
  if [ -n "${pg_pid}" ] && kill -0 "${pg_pid}" 2>/dev/null; then
    _LISTENER_PID="${pg_pid}"
    return 0
  fi

  return 1
}

_is_listener_running() {
  _find_listener_pid
}

# Kill a PID with TERM, wait up to 5s, then KILL
_kill_pid() {
  local pid="$1"
  kill "${pid}" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "${pid}" 2>/dev/null || return 0
    sleep 1
  done
  kill -9 "${pid}" 2>/dev/null || true
}

case "$1" in
  start)
    # Check if killed
    check_killed || exit 1

    if _is_listener_running; then
      echo "Already running (PID ${_LISTENER_PID})"
      # Sync telegram.pid if it drifted
      echo "${_LISTENER_PID}" > "${PIDFILE}"
      exit 1
    fi

    # Clean up stale tracking files
    rm -f "${PIDFILE}"
    rm -rf "${LOCKDIR}"

    nohup "${SCRIPT}" >> "${LOGFILE}" 2>&1 &
    echo $! > "${PIDFILE}"

    # Wait for the listener to write its own PID into listener.lock/pid,
    # confirming it actually started (up to 5s).
    started=false
    for _ in 1 2 3 4 5; do
      sleep 1
      if [ -f "${LOCKPID}" ]; then
        # Sync telegram.pid to the real listener PID
        real_pid="$(cat "${LOCKPID}" 2>/dev/null | tr -d '[:space:]')"
        if [ -n "${real_pid}" ] && kill -0 "${real_pid}" 2>/dev/null; then
          echo "${real_pid}" > "${PIDFILE}"
          echo "Started (PID ${real_pid})"
          started=true
          break
        fi
      fi
    done

    if [ "${started}" = false ]; then
      # The nohup child may have exited (lock conflict, missing deps, etc.)
      nohup_pid="$(cat "${PIDFILE}" 2>/dev/null)"
      if [ -n "${nohup_pid}" ] && kill -0 "${nohup_pid}" 2>/dev/null; then
        echo "Started (PID ${nohup_pid}) — but listener.lock not yet created"
      else
        rm -f "${PIDFILE}"
        echo "Failed to start (check ${LOGFILE})"
        exit 1
      fi
    fi
    ;;
  stop)
    if _is_listener_running; then
      _kill_pid "${_LISTENER_PID}"
      echo "Stopped (was PID ${_LISTENER_PID})"
    else
      echo "Not running"
    fi
    # Also kill any orphans that pgrep can find but _find_listener_pid missed
    pkill -TERM -f "messaging/telegram/listener\\.sh" 2>/dev/null || true
    # Clean up all tracking files
    rm -f "${PIDFILE}"
    rm -rf "${LOCKDIR}"
    ;;
  restart)
    $0 stop
    sleep 1
    $0 start
    ;;
  status)
    if _is_listener_running; then
      echo "Running (PID ${_LISTENER_PID})"
      # Sync telegram.pid if it drifted
      echo "${_LISTENER_PID}" > "${PIDFILE}"
    else
      echo "Stopped"
      # Clean up stale files
      [ -f "${PIDFILE}" ] && rm -f "${PIDFILE}"
      [ -d "${LOCKDIR}" ] && rm -rf "${LOCKDIR}"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
