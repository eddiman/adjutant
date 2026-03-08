#!/bin/bash
# scripts/common/opencode.sh — Safe opencode wrapper with child-process cleanup
#
# Problems solved:
#   1. `opencode run` spawns bash-language-server / yaml-language-server children
#      that survive after the parent exits. Over days these accumulate and eat RAM.
#   2. If `opencode run` hangs (e.g. post-sleep server degradation), callers block
#      indefinitely with no timeout or error signal.
#   3. After a sleep/wake cycle or overnight idle, the opencode serve server can enter
#      a degraded state OR its Anthropic auth token can expire silently. An HTTP ping
#      alone cannot detect token expiry — a real API call is required.
#
# Solutions:
#   1. Snapshot child PIDs before/after each call; kill any new stragglers.
#      Reaper also kills language servers whose direct parent is opencode serve
#      (meaning their opencode run parent has already exited).
#   2. opencode_run respects OPENCODE_TIMEOUT env var (seconds). The underlying
#      process is wrapped with `timeout`; on expiry returns exit code 124 and
#      cleans up children.
#   3. opencode_health_check probes the server with a fast call; if it fails or
#      times out it restarts opencode serve and waits up to 15s for recovery.
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
#   opencode_health_check  — two-stage probe (HTTP ping + real API call); restart if either fails

# Resolve opencode binary once
_OPENCODE_BIN="${_OPENCODE_BIN:-$(command -v opencode 2>/dev/null || echo "")}"

# PID file written by startup.sh for the opencode serve server
_OPENCODE_WEB_PID_FILE="${ADJ_DIR:-${HOME}/.adjutant}/state/opencode_web.pid"

# Port the opencode serve server listens on
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
  # Redirect watchdog to /dev/null so that the `sleep` grandchild it spawns does
  # not inherit the write-end of any $() pipe — otherwise the $() capture of the
  # caller hangs until sleep expires (typically 90s) even after the main command
  # exits and we kill the watchdog with SIGKILL.
  (sleep "${_secs}"; kill -TERM "${_child}" 2>/dev/null; sleep 1; kill -9 "${_child}" 2>/dev/null) </dev/null >/dev/null 2>&1 &
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

# --- _opencode_web_pid: return PID of the running opencode serve server, or empty ---
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
#   b) parented directly to ANY opencode serve process — meaning the transient
#      opencode run that spawned it has already exited, leaving it stranded.
#      This catches language servers under stale serve processes that are no
#      longer in opencode_web.pid (e.g. from a previous session or double-start).
#
# Call from the listener loop every N cycles as a safety net.
#
opencode_reap() {
  # Collect ALL running opencode serve PIDs — not just the tracked one.
  # This is the key fix: a language-server child of an unlisted/old serve process
  # would never be reaped if we only checked the PID-file entry.
  local _all_serve_pids
  _all_serve_pids="$(pgrep -f 'opencode serve' 2>/dev/null || true)"

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

    # Stranded under any serve process: parent is opencode serve itself.
    # A live ephemeral opencode run would be the direct parent, not the serve server.
    # If the parent IS a serve process, the run already exited and left this behind.
    local _serve_pid
    for _serve_pid in ${_all_serve_pids}; do
      if [ "${_ppid}" = "${_serve_pid}" ]; then
        kill -TERM "${_pid}" 2>/dev/null || true
        _killed=$((_killed + 1))
        break
      fi
    done
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

# --- opencode_health_check: probe server; restart opencode serve if degraded ---
#
# Two-stage probe:
#   1. HTTP ping  — verify the serve process is alive at all.
#   2. Real API call — cheap single-token Haiku call to verify the Anthropic
#      auth token is still valid. An HTTP 200 from the serve server does NOT
#      guarantee this; "Token refresh failed: 400" only surfaces when an actual
#      model call is attempted (as seen on 2026-03-06 when the 08:00 briefing
#      failed despite the server being up).
#
# If either stage fails, runs scripts/lifecycle/restart.sh (clean shutdown of
# all services + fresh startup), then waits up to 30s for recovery.
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
  local _api_probe_timeout=15
  local _http_rc=0

  # Stage 1: HTTP ping — verify the web process is alive at all.
  curl -sf --max-time "${_probe_timeout}" "http://localhost:${_OPENCODE_WEB_PORT}/" >/dev/null 2>&1 || _http_rc=$?

  if [ "${_http_rc}" -ne 0 ]; then
    if type adj_log &>/dev/null; then
      adj_log "opencode" "Health check stage 1 failed: HTTP ping (rc=${_http_rc}) — attempting restart"
    fi
    # Fall through to restart logic below.
  else
    # Stage 2: Real API probe — a cheap single-token call to verify the auth
    # token is still valid. HTTP ping alone cannot detect expired tokens.
    local _probe_response _probe_rc=0
    _probe_response="$(OPENCODE_TIMEOUT="${_api_probe_timeout}" opencode_run run "ping" \
      --model "anthropic/claude-haiku-4-5" --format json 2>&1)" || _probe_rc=$?

    # Accept the probe if it returned exit 0 OR produced any JSON event output
    # (even a model error event means auth succeeded and the server is healthy).
    if [ "${_probe_rc}" -eq 0 ] || echo "${_probe_response}" | grep -q '"type"'; then
      return 0
    fi

    if type adj_log &>/dev/null; then
      adj_log "opencode" "Health check stage 2 failed: API probe (rc=${_probe_rc}) — token likely expired, attempting restart"
    fi
  fi

  if type adj_log &>/dev/null; then
    adj_log "opencode" "Restarting opencode web via restart.sh for clean shutdown"
  fi

  local _adj_dir="${ADJ_DIR:-${HOME}/.adjutant}"
  local _restart_sh="${_adj_dir}/scripts/lifecycle/restart.sh"

  if [ ! -f "${_restart_sh}" ]; then
    if type adj_log &>/dev/null; then
      adj_log "opencode" "restart.sh not found at ${_restart_sh} — cannot restart"
    fi
    return 1
  fi

  # Run restart.sh in the background (it is interactive/verbose by design).
  # Redirect all output so it does not pollute the caller's stdout/stderr.
  bash "${_restart_sh}" >/dev/null 2>&1 &
  disown $!

  # Wait up to 30s for the server to come back up (restart.sh stops + starts
  # both the Telegram listener and opencode web, so allow extra time).
  local _wait=0
  while [ "${_wait}" -lt 30 ]; do
    sleep 1
    _wait=$((_wait + 1))
    curl -sf --max-time "${_probe_timeout}" "http://localhost:${_OPENCODE_WEB_PORT}/" >/dev/null 2>&1 && return 0
  done

  if type adj_log &>/dev/null; then
    adj_log "opencode" "opencode web did not recover within 30s after restart.sh"
  fi
  return 1
}
