#!/bin/bash
# Adjutant — AI vision analysis for received photos.
# Uses opencode run --file to pass an image to Claude for vision analysis.
#
# Usage:
#   vision.sh <image_path> [prompt]
#
# Called by:
#   - telegram photos.sh tg_handle_photo() after downloading a received photo
#
# Output: Prints vision analysis text to stdout.
# Returns exit code 0 on success, 1 on error.

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/logging.sh"
source "${COMMON}/platform.sh"
source "${COMMON}/opencode.sh"

ensure_path

MODEL_FILE="${ADJ_DIR}/state/telegram_model.txt"

# --- Args ---
IMAGE_PATH="${1:-}"
PROMPT="${2:-Describe what you see in this image. Be concise and informative.}"

if [ -z "${IMAGE_PATH}" ]; then
  echo "No image path provided."
  exit 1
fi

if [ ! -f "${IMAGE_PATH}" ]; then
  echo "Image file not found: ${IMAGE_PATH}"
  exit 1
fi

# --- Get vision model from config, fall back to session model ---
get_vision_model_from_config() {
  local in_vision=0
  while IFS= read -r line; do
    case "$line" in
      *"vision:"*) in_vision=1 ;;
      *"search:"*|*"screenshot:"*|*"news:"*|*"usage_tracking:"*) in_vision=0 ;;
      *"model:"*)
        if [ "$in_vision" -eq 1 ]; then
          echo "$line" | sed 's/.*model:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/' | tr -d '\n'
          return 0
        fi
        ;;
    esac
  done < "${ADJ_DIR}/adjutant.yaml" 2>/dev/null
  return 1
}

get_session_model() {
  if [ -f "${MODEL_FILE}" ]; then
    cat "${MODEL_FILE}" | tr -d '\n'
  else
    echo "anthropic/claude-haiku-4-5"
  fi
}

MODEL="$(get_vision_model_from_config || get_session_model)"
adj_log "vision" "Vision analysis: ${IMAGE_PATH} using ${MODEL}"

# --- Run opencode with image attached ---
# opencode run -f <file> attaches the image to the message context
RAW_FILE="$(mktemp)"
ERR_FILE="$(mktemp)"

opencode_run run \
  --model "${MODEL}" \
  --format json \
  -f "${IMAGE_PATH}" \
  -- "${PROMPT}" \
  > "${RAW_FILE}" 2>"${ERR_FILE}" || true

# --- Parse the streamed JSON output using jq ---
REPLY=""
ERROR_TYPE=""

while IFS= read -r line; do
  [ -z "$line" ] && continue
  
  type="$(echo "$line" | jq -r '.type // empty' 2>/dev/null)" || continue
  
  case "$type" in
    text)
      part="$(echo "$line" | jq -r '.part.text // empty' 2>/dev/null)"
      REPLY="${REPLY}${part}"
      ;;
    error)
      err_name="$(echo "$line" | jq -r '.error.name // empty' 2>/dev/null)"
      err_msg="$(echo "$line" | jq -r '.error.data.message // empty' 2>/dev/null)"
      if [[ "$err_msg" == *"Model not found"* ]] || [[ "$err_name" == *"ModelNotFoundError"* ]]; then
        ERROR_TYPE="model_not_found"
      fi
      ;;
  esac
done < "${RAW_FILE}"

rm -f "${RAW_FILE}" "${ERR_FILE}"

if [ "$ERROR_TYPE" = "model_not_found" ]; then
  echo "The selected model doesn't support vision. Try switching to claude-haiku-4-5 with /model anthropic/claude-haiku-4-5."
  exit 0
fi

if [ -n "${REPLY}" ]; then
  adj_log "vision" "Vision analysis complete for ${IMAGE_PATH}"
  printf '%s' "${REPLY}"
else
  adj_log "vision" "Vision analysis returned empty reply for ${IMAGE_PATH}"
  echo "I couldn't analyse this image — the model returned an empty response."
  exit 1
fi
