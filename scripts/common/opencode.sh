#!/bin/bash
# scripts/common/opencode.sh — Safe opencode wrapper with child-process cleanup
#
# Problems solved:
#   1. `opencode run` spawns bash-language-server / yaml-language-server children
#      that survive after the parent exits. Over days these accumulate and eat RAM.
#   2. If `opencode run` hangs (e.g. post-sleep server degradation), callers block
#      indefinitely with no timeout or error signal.
#   3. After a sleep/wake cycle the opencode web server can enter a degraded state;
#      subsequent `opencode run` calls hang trying to reach it.
#
# Solutions:
#   1. Snapshot child PIDs before/after each call; kill any new stragglers.
#      Reaper also kills language servers whose direct parent is opencode web
#      (meaning their opencode run parent has already exited).
#   2. opencode_run respects OPENCODE_TIMEOUT env var (seconds). The underlying
#      process is wrapped with `timeout`; on expiry returns exit code 124 and
#      cleans up children.
#   3. opencode_health_check probes the server with a fast call; if it fails or
#      times out it restarts opencode web and waits up to 15s for recovery.
#
# Usage:
#   source "${ADJ_DIR}/scripts/common/opencode.sh"
#
#   # Basic (no timeout):
#   opencode_run run --agent adjutant ...
#
#   # With timeout (seconds):
#   OPENCODE_TIMEOUT=90 opencode_run run --agent adjutant ...
#
#   # Health check before a critical call:
#   opencode_health_check || { echo "Server unrecoverable" >&2; exit 1; }
#   OPENCODE_TIMEOUT=90 opencode_run run --agent adjutant ...
#
# Provides:
#   opencode_run           — drop-in replacement for `opencode` with timeout + cleanup
#   opencode_reap          — periodic cleanup of orphaned language servers
#   opencode_health_check  — probe server health; restart opencode web if degraded

# Resolve opencode binary once
_OPENCODE_BIN="${_OPENCODE_BIN:-$(command -v opencode 2>/dev/null || echo "")}"

# PID file written by startup.sh for the opencode web server
_OPENCODE_WEB_PID_FILE="${ADJ_DIR:-${HOME}/.adjutant}/state/opencode_web.pid"

# Port the opencode web server listens on
_OPENCODE_WEB_PORT="${OPENCODE_WEB_PORT:-4096}"

# --- _adj_timeout: portable timeout wrapper (works without GNU coreutils) ---
#
# Usage: _adj_timeout <seconds> <command> [args...]
# Returns the command's exit code, or 124 on timeout.
#
_adj_timeout() {
  local _secs="$1"; shift
  # Prefer system timeout / gtimeout if available
  if command -v timeout &>/dev/null; then
    timeout "${_secs}" "$@"
    return $?
  fi
  if command -v gtimeout &>/dev/null; then
    gtimeout "${_secs}" "$@"
    return $?
  fi
  # Shell-native fallback: run in background, sleep, then kill
  "$@" &
  local _child=$!
  (sleep "${_secs}"; kill -TERM "${_child}" 2>/dev/null; sleep 1; kill -9 "${_child}" 2>/dev/null) &
  local _watchdog=$!
  wait "${_child}" 2>/dev/null
  local _rc=$?
  kill -9 "${_watchdog}" 2>/dev/null
  wait "${_watchdog}" 2>/dev/null || true
  # wait returns 127 if process already gone — treat anything >125 as timeout
  if [ "${_rc}" -gt 125 ]; then
    return 124
  fi
  return "${_rc}"
}

# --- _opencode_web_pid: return PID of the running opencode web server, or empty ---
_opencode_web_pid() {
  [ -f "${_OPENCODE_WEB_PID_FILE}" ] || return 0
  local _pid
  _pid="$(cat "${_OPENCODE_WEB_PID_FILE}" 2>/dev/null | tr -d '[:space:]')"
  [[ "${_pid}" =~ ^[0-9]+$ ]] || return 0
  kill -0 "${_pid}" 2>/dev/null && echo "${_pid}" || true
}

# --- opencode_run: run opencode with optional timeout and child cleanup ---
#
# Environment:
#   OPENCODE_TIMEOUT  — seconds before the call is killed (default: no timeout)
#
opencode_run() {
  if [ -z "${_OPENCODE_BIN}" ]; then
    echo "opencode not found on PATH" >&2
    return 1
  fi

  # Snapshot: language-server PIDs BEFORE we start
  local _before_pids
  _before_pids="$(pgrep -f 'bash-language-server\|yaml-language-server' 2>/dev/null | sort || true)"

  local _rc=0

  if [ -n "${OPENCODE_TIMEOUT:-}" ]; then
    _adj_timeout "${OPENCODE_TIMEOUT}" "${_OPENCODE_BIN}" "$@" || _rc=$?
  else
    "${_OPENCODE_BIN}" "$@" || _rc=$?
  fi

  # Snapshot: PIDs AFTER opencode exits
  local _after_pids
  _after_pids="$(pgrep -f 'bash-language-server\|yaml-language-server' 2>/dev/null | sort || true)"

  # Diff: any new PIDs are orphans from our invocation — kill them
  local _new_pids
  _new_pids="$(comm -13 <(echo "${_before_pids}") <(echo "${_after_pids}") 2>/dev/null || true)"

  if [ -n "${_new_pids}" ]; then
    local _pid
    for _pid in ${_new_pids}; do
      kill -0 "${_pid}" 2>/dev/null && kill -TERM "${_pid}" 2>/dev/null || true
    done
    sleep 1
    for _pid in ${_new_pids}; do
      kill -0 "${_pid}" 2>/dev/null && kill -9 "${_pid}" 2>/dev/null || true
    done
  fi

  return ${_rc}
}

# --- opencode_reap: periodic cleanup of ALL orphaned language servers ---
#
# Kills any bash-language-server or yaml-language-server that is:
#   a) parented to PID 1 or a gone process (classic orphan), OR
#   b) parented directly to the opencode web server — meaning the transient
#      opencode run that spawned it has already exited, leaving it stranded.
#
# Call from the listener loop every N cycles as a safety net.
#
opencode_reap() {
  local _web_pid
  _web_pid="$(_opencode_web_pid)"

  local _pids
  _pids="$(pgrep -f 'bash-language-server\|yaml-language-server' 2>/dev/null || true)"
  [ -z "${_pids}" ] && return 0

  local _pid _ppid _killed=0
  for _pid in ${_pids}; do
    _ppid="$(ps -o ppid= -p "${_pid}" 2>/dev/null | tr -d ' ')" || continue

    # Orphaned: parent is gone or is PID 1
    if [ "${_ppid}" = "1" ] || ! kill -0 "${_ppid}" 2>/dev/null; then
      kill -TERM "${_pid}" 2>/dev/null || true
      _killed=$((_killed + 1))
      continue
    fi

    # Stranded under web server: parent is opencode web itself.
    # A live ephemeral opencode run would be the direct parent, not the web server.
    # If the parent IS the web server, the run already exited and left this behind.
    if [ -n "${_web_pid}" ] && [ "${_ppid}" = "${_web_pid}" ]; then
      kill -TERM "${_pid}" 2>/dev/null || true
      _killed=$((_killed + 1))
    fi
  done

  # Give them a moment, then force-kill survivors
  if [ "${_killed}" -gt 0 ]; then
    sleep 1
    for _pid in ${_pids}; do
      kill -0 "${_pid}" 2>/dev/null && kill -9 "${_pid}" 2>/dev/null || true
    done
    if type adj_log &>/dev/null; then
      adj_log "opencode" "Reaped ${_killed} orphaned language-server process(es)"
    fi
  fi
}

# --- opencode_health_check: probe server; restart opencode web if degraded ---
#
# Runs a minimal opencode call with a short timeout to verify the server is
# responsive. If it fails or times out, kills and restarts opencode web, then
# waits up to 15s for recovery.
#
# Returns:
#   0  — server is healthy (or was successfully restarted)
#   1  — server is unrecoverable
#
opencode_health_check() {
  if [ -z "${_OPENCODE_BIN}" ]; then
    return 1
  fi

  local _probe_timeout=5
  local _rc=0

  # Probe: HTTP GET against the web server — this actually tests server health
  # curl --max-time is available on macOS without coreutils
  curl -sf --max-time "${_probe_timeout}" "http://localhost:${_OPENCODE_WEB_PORT}/" >/dev/null 2>&1 || _rc=$?

  if [ "${_rc}" -eq 0 ]; then
    return 0
  fi

  if type adj_log &>/dev/null; then
    adj_log "opencode" "Health check failed (rc=${_rc}) — attempting opencode web restart"
  fi

  # Kill existing web server
  local _web_pid
  _web_pid="$(_opencode_web_pid)"
  if [ -n "${_web_pid}" ]; then
    kill -TERM "${_web_pid}" 2>/dev/null || true
    sleep 2
    kill -0 "${_web_pid}" 2>/dev/null && kill -9 "${_web_pid}" 2>/dev/null || true
  fi

  # Restart web server
  local _adj_dir="${ADJ_DIR:-${HOME}/.adjutant}"
  local _startup="${_adj_dir}/scripts/startup.sh"
  if [ -f "${_startup}" ]; then
    bash "${_startup}" restart-web >/dev/null 2>&1 &
    disown $!
  else
    # Fallback: start directly
    nohup "${_OPENCODE_BIN}" web --mdns \
      >"${_adj_dir}/state/opencode_web.log" 2>&1 &
    echo $! > "${_OPENCODE_WEB_PID_FILE}"
    disown $!
  fi

  # Wait up to 15s for the server to respond
  local _wait=0
  while [ "${_wait}" -lt 15 ]; do
    sleep 1
    _wait=$((_wait + 1))
    curl -sf --max-time "${_probe_timeout}" "http://localhost:${_OPENCODE_WEB_PORT}/" >/dev/null 2>&1 && return 0
  done

  if type adj_log &>/dev/null; then
    adj_log "opencode" "opencode web restart did not recover within 15s"
  fi
  return 1
}
