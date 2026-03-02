# Plugin (Capability) Guide

A capability is a self-contained script that gives Adjutant a new skill — taking screenshots, querying an API, reading files, sending notifications to third-party services, etc.

The agent can invoke capabilities directly via bash tool calls. Capabilities can also be wired to slash commands in `commands.sh`.

---

## Anatomy of a Capability

```
scripts/capabilities/
└── <name>/
    └── <name>.sh          # Entry script (required)
    └── *.sh               # Supporting scripts (optional)
    └── *.mjs / *.py       # Helper processes (optional)
```

Each capability lives in its own subdirectory. The entry script is the only required file.

---

## Entry Script Contract

The entry script must:

1. Load common utilities from `scripts/common/`
2. Accept arguments as positional parameters
3. Print `OK:<result>` on success or `ERROR:<reason>` on failure to stdout
4. Exit 0 on success, non-zero on failure

```bash
#!/bin/bash
# scripts/capabilities/<name>/<name>.sh
#
# One-line description of what this capability does.
#
# Usage:
#   <name>.sh <arg1> [arg2]
#
# Output:
#   OK:<result>    — on success
#   ERROR:<reason> — on failure

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/env.sh"
source "${COMMON}/logging.sh"
source "${COMMON}/platform.sh"

# Validate arguments
ARG1="${1:-}"
if [ -z "${ARG1}" ]; then
  echo "ERROR: No argument provided. Usage: <name>.sh <arg1>"
  exit 1
fi

adj_log "<name>" "Starting with arg: ${ARG1}"

# --- Do the work ---
RESULT="$(do_something "${ARG1}")" || {
  adj_log "<name>" "Failed: ${ARG1}"
  echo "ERROR: Could not process ${ARG1}"
  exit 1
}

adj_log "<name>" "Completed: ${ARG1}"
echo "OK:${RESULT}"
```

---

## Minimal Working Example

Here is the simplest possible capability — a date/time lookup:

```bash
#!/bin/bash
# scripts/capabilities/datetime/datetime.sh
#
# Returns the current date and time in a human-readable format.
#
# Usage:
#   datetime.sh [timezone]
#
# Output:
#   OK:<date string>
#   ERROR:<reason>

COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/logging.sh"

TZ_ARG="${1:-}"

if [ -n "${TZ_ARG}" ]; then
  RESULT="$(TZ="${TZ_ARG}" date '+%A, %B %-d %Y at %H:%M %Z' 2>/dev/null)" || {
    echo "ERROR: Unknown timezone: ${TZ_ARG}"
    exit 1
  }
else
  RESULT="$(date '+%A, %B %-d %Y at %H:%M %Z')"
fi

adj_log "datetime" "Queried time (tz=${TZ_ARG:-local})"
echo "OK:${RESULT}"
```

---

## Using Credentials

If your capability needs credentials, load them with `env.sh`:

```bash
source "${COMMON}/env.sh"

API_KEY="$(get_credential MY_SERVICE_API_KEY)"
if [ -z "${API_KEY}" ]; then
  echo "ERROR: MY_SERVICE_API_KEY not set in .env"
  exit 1
fi
```

Add the credential to `.env.example` so users know to configure it:

```
MY_SERVICE_API_KEY=your_api_key_here
```

---

## Wiring a Slash Command

To make your capability available as a `/command` in chat, add a handler to `scripts/messaging/telegram/commands.sh` (or your backend's equivalent):

```bash
cmd_datetime() {
  local message_id="$1"
  local tz="${2:-}"

  RESULT="$(bash "${ADJ_DIR}/scripts/capabilities/datetime/datetime.sh" "${tz}")"

  if [[ "${RESULT}" == OK:* ]]; then
    msg_send_text "${RESULT#OK:}" "${message_id}"
  else
    msg_send_text "Could not get date/time: ${RESULT#ERROR:}" "${message_id}"
  fi
}
```

Then register the command in `dispatch.sh`'s `case` block:

```bash
/datetime)      cmd_datetime "${message_id}" ;;
/datetime\ *)   cmd_datetime "${message_id}" "${text#/datetime }" ;;
```

And add it to the help text in `cmd_help`.

---

## Wiring the Agent

The agent (OpenCode) can call any capability directly via the bash tool. No registration is needed — just document the capability in `.opencode/agents/adjutant.md` so the agent knows it exists:

```markdown
## Available Tools

### datetime
Get the current date and time.
Usage: bash scripts/capabilities/datetime/datetime.sh [timezone]
Output: OK:<date string>
```

---

## Sending Output to the User

Capabilities do not send messages themselves — they return results to the caller. The caller (a `cmd_*` function or the agent) is responsible for sending the reply.

If your capability generates a file (e.g., a screenshot, a PDF, a CSV), return its path:

```bash
echo "OK:${OUTPUT_FILE}"
```

The caller can then pass it to `msg_send_photo` or `msg_send_document`.

---

## Logging

Always log the start and end of significant operations using `adj_log`:

```bash
adj_log "<name>" "Starting: ${ARG}"
# ... work ...
adj_log "<name>" "Completed: ${ARG}"
```

Log failures with enough context to debug:

```bash
adj_log "<name>" "FAILED for ${ARG}: ${ERROR_MSG}"
```

Logs go to `state/adjutant.log`. View with `adjutant logs`.

---

## Error Handling

- Use `set -euo pipefail` only if every external command in your script is expected to succeed. Prefer explicit error checking for commands that may legitimately fail.
- Always print `ERROR:<reason>` to stdout (not stderr) so the caller can detect and relay failures.
- Clean up temp files in a `trap`:

```bash
TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT
```

---

## Reference: Screenshot Capability

`scripts/capabilities/screenshot/screenshot.sh` is the most complete example:

- Validates the URL argument
- Loads credentials via `env.sh`
- Uses a helper Node script for Playwright
- Falls back from `sendPhoto` to `sendDocument` on error
- Calls the vision capability for an automatic caption
- Returns `OK:<filepath>` on success

Read it before writing any capability that involves external processes or file output.
