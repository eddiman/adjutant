#!/bin/bash
# scripts/messaging/telegram/commands.sh — All /command handlers
#
# Extracted from the monolithic telegram_listener.sh.
# Each cmd_*() function handles one slash command.
#
# These are backend-agnostic — they use the adaptor interface (msg_send_text,
# msg_send_photo, msg_react, msg_typing) not Telegram API directly.
#
# Requires: ADJ_DIR, msg_send_text, msg_react, msg_typing (from adaptor/send.sh)
# Requires: adj_log, fmt_ts (from logging.sh)
# Requires: set_paused, clear_paused (from lockfiles.sh)
#
# Provides: cmd_status, cmd_pause, cmd_resume, cmd_kill, cmd_pulse,
#           cmd_restart, cmd_reflect_request, cmd_reflect_confirm,
#           cmd_help, cmd_model, cmd_screenshot, cmd_search, cmd_kb

PENDING_REFLECT_FILE="${ADJ_DIR}/state/pending_reflect"
MODEL_FILE="${ADJ_DIR}/state/telegram_model.txt"
SCREENSHOTS_DIR="${ADJ_DIR}/screenshots"

mkdir -p "${SCREENSHOTS_DIR}"

# --- /status ---
cmd_status() {
  local message_id="${1:-}"

  local status_output
  status_output=$("${ADJ_DIR}/scripts/observability/status.sh" 2>/dev/null) || status_output="Could not retrieve status."

  msg_send_text "${status_output}" "${message_id}"
}

# --- /pause ---
cmd_pause() {
  local message_id="${1:-}"

  set_paused
  local ts
  ts="$(date '+%H:%M %d.%m.%Y')"
  echo "${ts} — Paused via Telegram command." >> "${ADJ_DIR}/journal/$(date '+%Y-%m-%d').md"
  msg_send_text "Got it, I've paused. Send /resume whenever you want me back." "${message_id}"
  adj_log telegram "Adjutant paused via Telegram."
}

# --- /resume ---
cmd_resume() {
  local message_id="${1:-}"

  clear_paused
  local ts
  ts="$(date '+%H:%M %d.%m.%Y')"
  echo "${ts} — Resumed via Telegram command." >> "${ADJ_DIR}/journal/$(date '+%Y-%m-%d').md"
  msg_send_text "I'm back online and keeping an eye on things." "${message_id}"
  adj_log telegram "Adjutant resumed via Telegram."
}

# --- /kill ---
cmd_kill() {
  local message_id="${1:-}"

  adj_log telegram "EMERGENCY KILL SWITCH activated via Telegram."

  # Background the kill script so we can send reply before listener dies
  "${ADJ_DIR}/scripts/lifecycle/emergency_kill.sh" &

  msg_send_text "Emergency kill switch activated. Shutting down all systems..." "${message_id}"
}

# --- /pulse ---
cmd_pulse() {
  local message_id="${1:-}"

  msg_send_text "On it — running a pulse check now. Give me a moment." "${message_id}"
  adj_log telegram "Pulse triggered via Telegram."

  local opencode_bin
  opencode_bin="$(which opencode 2>/dev/null || echo '')"

  if [ -z "${opencode_bin}" ]; then
    local heartbeat_file="${ADJ_DIR}/state/last_heartbeat.json"
    if [ -f "${heartbeat_file}" ]; then
      # Extract timestamp from JSON — no Python
      local raw_ts
      raw_ts="$(grep -o '"timestamp":"[^"]*"' "${heartbeat_file}" 2>/dev/null | head -1 | cut -d'"' -f4)"
      [ -z "${raw_ts}" ] && raw_ts="$(grep -o '"last_run":"[^"]*"' "${heartbeat_file}" 2>/dev/null | head -1 | cut -d'"' -f4)"
      local fmt_time
      fmt_time="$(fmt_ts "${raw_ts}")"

      # Extract findings/summary — no Python
      local summary
      summary="$(grep -o '"findings":"[^"]*"' "${heartbeat_file}" 2>/dev/null | head -1 | cut -d'"' -f4)"
      [ -z "${summary}" ] && summary="$(grep -o '"summary":"[^"]*"' "${heartbeat_file}" 2>/dev/null | head -1 | cut -d'"' -f4)"
      [ -z "${summary}" ] && summary="Nothing notable recorded."

      msg_send_text "Here's what I last recorded (${fmt_time}):

${summary}" "${message_id}"
    else
      msg_send_text "I don't have any pulse data yet. Run a pulse from inside OpenCode first and I'll have something to show you." "${message_id}"
    fi
    return
  fi

  local pulse_prompt="${ADJ_DIR}/prompts/pulse.md"
  if [ ! -f "${pulse_prompt}" ]; then
    msg_send_text "I can't find the pulse prompt — expected it at ${pulse_prompt}." "${message_id}"
    return
  fi

  local result
  local _pulse_exit
  local _before_lsp _after_lsp _orphan_lsp
  _before_lsp="$(pgrep -f 'bash-language-server' 2>/dev/null | sort || true)"
  result="$(_adj_timeout 240 "${opencode_bin}" run --dir "${ADJ_DIR}" --format json "$(cat "${pulse_prompt}")" 2>>"${ADJ_DIR}/state/adjutant.log" \
    | grep '"type":"text"' \
    | grep -o '"text":"[^"]*"' \
    | sed 's/^"text":"//;s/"$//' \
    | tr -d '\000-\010\013-\037' \
    | paste -sd '' \
    | tail -c 3800)"
  _pulse_exit=$?
  _after_lsp="$(pgrep -f 'bash-language-server' 2>/dev/null | sort || true)"
  _orphan_lsp="$(comm -13 <(echo "${_before_lsp}") <(echo "${_after_lsp}") 2>/dev/null || true)"
  [ -n "${_orphan_lsp}" ] && { for _p in ${_orphan_lsp}; do kill "${_p}" 2>/dev/null || true; done; }
  if [ ${_pulse_exit} -eq 124 ]; then
    adj_log telegram "Pulse timed out after 240s (exit 124)."
    result="The pulse check timed out after 4 minutes."
  elif [ ${_pulse_exit} -ne 0 ] && [ -z "${result}" ]; then
    adj_log telegram "Pulse failed with exit code ${_pulse_exit} and no output."
    result="The pulse check ran into an error (exit ${_pulse_exit}). Check adjutant.log for details."
  fi
  adj_log telegram "Pulse completed via Telegram (exit ${_pulse_exit}, output: $(echo "${result}" | wc -w | tr -d ' ') words)."
  msg_send_text "${result}" "${message_id}"
}

# --- /restart ---
cmd_restart() {
  local message_id="${1:-}"

  msg_send_text "Restarting all services..." "${message_id}"
  adj_log telegram "Restart triggered via Telegram."

  # Run restart script in background
  nohup "${ADJ_DIR}/scripts/lifecycle/restart.sh" > /dev/null 2>&1 &

  # Brief pause to allow listener to potentially be restarted
  sleep 2

  msg_send_text "Services restarted. If I don't respond, I'm still restarting — try again in 10 seconds." "${message_id}"
  adj_log telegram "Restart completed via Telegram."
}

# --- /reflect (request confirmation) ---
cmd_reflect_request() {
  local message_id="${1:-}"

  touch "${PENDING_REFLECT_FILE}"
  msg_send_text "Just so you know — a full reflection uses Opus, which costs roughly \$0.10–0.30. Reply */confirm* if you'd like me to go ahead, or send anything else to cancel." "${message_id}"
  adj_log telegram "Reflect requested via Telegram — awaiting confirmation."
}

# --- /confirm (execute reflection) ---
cmd_reflect_confirm() {
  local message_id="${1:-}"

  rm -f "${PENDING_REFLECT_FILE}"
  msg_send_text "Great, I'm starting the reflection now — this usually takes a minute or two." "${message_id}"
  adj_log telegram "Reflect confirmed via Telegram."

  local opencode_bin
  opencode_bin="$(which opencode 2>/dev/null || echo '')"

  if [ -z "${opencode_bin}" ]; then
    msg_send_text "I can't find the opencode CLI, so I'm not able to run the reflection from here. You can trigger it manually with /reflect inside OpenCode." "${message_id}"
    return
  fi

  local reflect_prompt="${ADJ_DIR}/prompts/review.md"
  if [ ! -f "${reflect_prompt}" ]; then
    msg_send_text "I can't find the reflection prompt — something may be misconfigured." "${message_id}"
    return
  fi

  local result
  local _reflect_exit
  local _before_lsp _after_lsp _orphan_lsp
  _before_lsp="$(pgrep -f 'bash-language-server' 2>/dev/null | sort || true)"
  result="$(_adj_timeout 300 "${opencode_bin}" run --dir "${ADJ_DIR}" --model claude-opus-4-5 --format json "$(cat "${reflect_prompt}")" 2>>"${ADJ_DIR}/state/adjutant.log" \
    | grep '"type":"text"' \
    | grep -o '"text":"[^"]*"' \
    | sed 's/^"text":"//;s/"$//' \
    | tr -d '\000-\010\013-\037' \
    | paste -sd '' \
    | tail -c 3800)"
  _reflect_exit=$?
  _after_lsp="$(pgrep -f 'bash-language-server' 2>/dev/null | sort || true)"
  _orphan_lsp="$(comm -13 <(echo "${_before_lsp}") <(echo "${_after_lsp}") 2>/dev/null || true)"
  [ -n "${_orphan_lsp}" ] && { for _p in ${_orphan_lsp}; do kill "${_p}" 2>/dev/null || true; done; }
  if [ ${_reflect_exit} -eq 124 ]; then
    adj_log telegram "Reflect timed out after 300s (exit 124)."
    result="The reflection timed out after 5 minutes. Try again from inside OpenCode."
  elif [ ${_reflect_exit} -ne 0 ] && [ -z "${result}" ]; then
    adj_log telegram "Reflect failed with exit code ${_reflect_exit} and no output."
    result="The reflection ran into an error (exit ${_reflect_exit}). Check adjutant.log for details."
  fi
  adj_log telegram "Reflect completed via Telegram (exit ${_reflect_exit}, output: $(echo "${result}" | wc -w | tr -d ' ') words)."
  msg_send_text "${result}" "${message_id}"
}

# --- /help ---
cmd_help() {
  local message_id="${1:-}"

  msg_send_text "Here's what I can do for you:

You can just talk to me naturally — ask about your projects, priorities, upcoming events, or anything in your files and I'll look it up and answer.

Or use a command:
/status — I'll tell you if I'm running or paused, show registered scheduled jobs, and when I last checked in.
/pulse — I'll run a quick check across your projects and summarise what I find.
/restart — Restart all services (listener, opencode web).
/reflect — I'll do a deeper Opus reflection (I'll ask you to confirm first).
/screenshot <url> — Take a full-page screenshot of any website and send it here.
/search <query> — Search the web via Brave Search and return top results.
/kb — List knowledge bases or query one (/kb query <name> <question>).
/schedule — List scheduled jobs or manage them (/schedule run <name>, /schedule enable <name>, /schedule disable <name>).
/pause — I'll stop monitoring until you're ready for me to resume.
/resume — I'll pick back up where I left off.
/model — Show current model, or switch with /model <name>.
/kill — Emergency shutdown. Terminates all Adjutant processes and locks system. Use \`adjutant start\` to recover.
/help — Shows this message.

You can also send me a photo — I'll store it locally and tell you what I see." "${message_id}"
}

# --- /model [name] ---
cmd_model() {
  local arg="${1:-}"
  local message_id="${2:-}"

  local current_model
  if [ -f "${MODEL_FILE}" ]; then
    current_model="$(cat "${MODEL_FILE}" | tr -d '\n')"
  else
    current_model="anthropic/claude-haiku-4-5"
  fi

  if [ -z "${arg}" ]; then
    local model_list
    model_list="$(opencode models 2>/dev/null | head -30)"
    msg_send_text "Current model: *${current_model}*

Available models (first 30 — full list at \`opencode models\`):
\`\`\`
${model_list}
\`\`\`

Switch with: /model <name>" "${message_id}"
    return
  fi

  local new_model="${arg}"

  if ! opencode models 2>/dev/null | grep -qxF "${new_model}"; then
    msg_send_text "I don't recognise that model. Run /model to see available options." "${message_id}"
    return
  fi

  echo "${new_model}" > "${MODEL_FILE}"
  msg_send_text "Switched to *${new_model}*." "${message_id}"
  adj_log telegram "Model switched to ${new_model}"
}

# --- /screenshot <url> ---
cmd_screenshot() {
  local url="${1:-}"
  local message_id="${2:-}"

  if [ -z "${url}" ]; then
    msg_send_text "Please provide a URL. Example: /screenshot https://example.com" "${message_id}"
    return
  fi

  adj_log telegram "Screenshot requested: ${url}"
  msg_react "${message_id}"

  (
    msg_typing start "ss_${message_id}"

    local result
    result="$(bash "${ADJ_DIR}/scripts/capabilities/screenshot/screenshot.sh" "${url}" 2>>"${ADJ_DIR}/state/adjutant.log")"
    local ss_exit=$?

    msg_typing stop "ss_${message_id}"

    if [ ${ss_exit} -ne 0 ] || [[ "${result}" == ERROR:* ]]; then
      local err_msg="${result#ERROR: }"
      msg_send_text "Screenshot failed: ${err_msg}" "${message_id}"
      adj_log telegram "Screenshot failed for ${url}: ${err_msg}"
    else
      # screenshot.sh already sent the photo; just log success
      adj_log telegram "Screenshot sent for ${url}"
    fi
  ) </dev/null >/dev/null 2>&1 &
  disown $!
}

# --- /search <query> ---
cmd_search() {
  local query="${1:-}"
  local message_id="${2:-}"

  if [ -z "${query}" ]; then
    msg_send_text "Please provide a search query. Example: /search latest AI news" "${message_id}"
    return
  fi

  adj_log telegram "Search requested: ${query}"
  msg_react "${message_id}"

  (
    msg_typing start "search_${message_id}"

    local result
    result="$(bash "${ADJ_DIR}/scripts/capabilities/search/search.sh" "${query}" 2>>"${ADJ_DIR}/state/adjutant.log")"
    local search_exit=$?

    msg_typing stop "search_${message_id}"

    if [ ${search_exit} -ne 0 ] || [[ "${result}" == ERROR:* ]]; then
      local err_msg="${result#ERROR:}"
      msg_send_text "Search failed: ${err_msg}" "${message_id}"
      adj_log telegram "Search failed for '${query}': ${err_msg}"
    else
      msg_send_text "${result#OK:}" "${message_id}"
      adj_log telegram "Search results sent for: ${query}"
    fi
  ) </dev/null >/dev/null 2>&1 &
  disown $!
}

# --- /kb [list|query <name> <question>] ---
cmd_kb() {
  local action="${1:-}"
  local message_id="${2:-}"

  # Source KB management functions
  source "${ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  if [ -z "${action}" ] || [ "${action}" = "list" ]; then
    # List all KBs
    local count
    count="$(kb_count)"
    if [ "${count}" -eq 0 ]; then
      msg_send_text "No knowledge bases registered yet. Create one with \`adjutant kb create\`." "${message_id}"
      return
    fi

    local list_text="*Knowledge Bases* (${count}):"$'\n'
    while IFS=$'\t' read -r name desc path access; do
      list_text="${list_text}"$'\n'"• *${name}* (${access}) — ${desc}"
    done < <(kb_list)
    list_text="${list_text}"$'\n'$'\n'"Query with: /kb query <name> <question>"

    msg_send_text "${list_text}" "${message_id}"
    return
  fi

  if [ "${action}" = "query" ]; then
    local kb_name="${3:-}"
    # Everything after the kb name is the query
    shift 3 2>/dev/null || true
    local query="$*"

    if [ -z "${kb_name}" ] || [ -z "${query}" ]; then
      msg_send_text "Usage: /kb query <name> <your question>" "${message_id}"
      return
    fi

    if ! kb_exists "${kb_name}"; then
      msg_send_text "Knowledge base '${kb_name}' not found. Run /kb list to see available KBs." "${message_id}"
      return
    fi

    msg_react "${message_id}"

    (
      msg_typing start "kb_${message_id}"

      local result
      result="$(bash "${ADJ_DIR}/scripts/capabilities/kb/query.sh" "${kb_name}" "${query}" 2>>"${ADJ_DIR}/state/adjutant.log")"
      local kb_exit=$?

      msg_typing stop "kb_${message_id}"

      if [ ${kb_exit} -ne 0 ] || [ -z "${result}" ]; then
        msg_send_text "KB query failed or returned empty. Check the KB has content." "${message_id}"
        adj_log telegram "KB query failed for ${kb_name}: ${query}"
      else
        msg_send_text "[${kb_name}] ${result}" "${message_id}"
        adj_log telegram "KB query answered from ${kb_name}"
      fi
    ) </dev/null >/dev/null 2>&1 &
    disown $!
    return
  fi

  # Unknown action
  msg_send_text "Usage: /kb list — show knowledge bases
/kb query <name> <question> — ask a KB" "${message_id}"
}

# --- /schedule [list|run <name>|enable <name>|disable <name>] ---
cmd_schedule() {
  local input="${1:-}"
  local message_id="${2:-}"

  # Parse subcommand and optional name argument
  local action name
  action="$(echo "${input}" | awk '{print $1}')"
  name="$(echo "${input}" | awk '{print $2}')"

  # Source schedule management functions
  source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"

  if [ -z "${action}" ] || [ "${action}" = "list" ]; then
    local count
    count="$(schedule_count)"
    if [ "${count}" -eq 0 ]; then
      msg_send_text "No scheduled jobs registered yet. Add one with \`adjutant schedule add\`." "${message_id}"
      return
    fi

    local list_text="*Scheduled Jobs* (${count}):"$'\n'
    while IFS=$'\t' read -r jname desc sched script log enabled notify kb_name kb_operation; do
      local flag=""
      [ "${enabled}" = "false" ] && flag=" _(disabled)_"
      list_text="${list_text}"$'\n'"• *${jname}*${flag} — ${sched}"$'\n'"  ${desc}"
    done < <(schedule_list)
    list_text="${list_text}"$'\n'$'\n'"Manage: /schedule run <name> | /schedule enable <name> | /schedule disable <name>"

    msg_send_text "${list_text}" "${message_id}"
    return
  fi

  if [ "${action}" = "run" ]; then
    if [ -z "${name}" ]; then
      msg_send_text "Usage: /schedule run <name>" "${message_id}"
      return
    fi

    if ! schedule_exists "${name}"; then
      msg_send_text "Job '${name}' not found. Use /schedule list to see registered jobs." "${message_id}"
      return
    fi

    msg_react "${message_id}"

    (
      msg_typing start "sched_${message_id}"

      source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh"
      local script_raw log_raw
      script_raw="$(schedule_get_field "${name}" script)"
      local script_path
      case "${script_raw}" in
        /*) script_path="${script_raw}" ;;
        *)  script_path="${ADJ_DIR}/${script_raw}" ;;
      esac

      local result run_exit
      result="$(bash "${script_path}" 2>>"${ADJ_DIR}/state/adjutant.log")" || run_exit=$?
      run_exit="${run_exit:-0}"

      msg_typing stop "sched_${message_id}"

      if [ "${run_exit}" -ne 0 ] || [ -z "${result}" ]; then
        msg_send_text "[${name}] Job completed (exit ${run_exit})." "${message_id}"
      else
        msg_send_text "[${name}] ${result}" "${message_id}"
      fi
      adj_log telegram "Schedule job '${name}' run via Telegram (exit ${run_exit})"
    ) </dev/null >/dev/null 2>&1 &
    disown $!
    return
  fi

  if [ "${action}" = "enable" ]; then
    if [ -z "${name}" ]; then
      msg_send_text "Usage: /schedule enable <name>" "${message_id}"
      return
    fi
    if ! schedule_exists "${name}"; then
      msg_send_text "Job '${name}' not found. Use /schedule list to see registered jobs." "${message_id}"
      return
    fi
    schedule_set_enabled "${name}" "true"
    msg_send_text "Job *${name}* enabled — crontab entry installed." "${message_id}"
    adj_log telegram "Schedule job '${name}' enabled via Telegram"
    return
  fi

  if [ "${action}" = "disable" ]; then
    if [ -z "${name}" ]; then
      msg_send_text "Usage: /schedule disable <name>" "${message_id}"
      return
    fi
    if ! schedule_exists "${name}"; then
      msg_send_text "Job '${name}' not found. Use /schedule list to see registered jobs." "${message_id}"
      return
    fi
    schedule_set_enabled "${name}" "false"
    msg_send_text "Job *${name}* disabled — crontab entry removed." "${message_id}"
    adj_log telegram "Schedule job '${name}' disabled via Telegram"
    return
  fi

  # Unknown subcommand
  msg_send_text "Usage:
/schedule list — show all scheduled jobs
/schedule run <name> — run a job immediately
/schedule enable <name> — enable a job
/schedule disable <name> — disable a job" "${message_id}"
}
