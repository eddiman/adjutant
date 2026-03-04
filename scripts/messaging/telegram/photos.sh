#!/bin/bash
# scripts/messaging/telegram/photos.sh — Telegram photo download, storage, vision routing
#
# Extracted from telegram_listener.sh handle_photo() function.
# Downloads photos from Telegram, saves locally, routes to vision analysis.
#
# Requires: TELEGRAM_BOT_TOKEN (set before sourcing)
# Requires: ADJ_DIR (from paths.sh)
# Requires: msg_send_text, msg_react, msg_typing (from send.sh)
# Requires: adj_log (from logging.sh)
#
# Provides:
#   tg_download_photo  "file_id" → prints local file path on stdout
#   tg_handle_photo    "from_id" "message_id" "file_id" ["caption"]

PHOTOS_DIR="${ADJ_DIR}/photos"
PHOTO_DEDUP_DIR="${ADJ_DIR}/state/photo_dedup"
mkdir -p "${PHOTOS_DIR}" "${PHOTO_DEDUP_DIR}"

# Clean stale dedup markers older than 60 seconds
_photo_dedup_cleanup() {
  find "${PHOTO_DEDUP_DIR}" -type f -mmin +1 -delete 2>/dev/null || true
}

# Check if a photo file_id was recently processed (within 60s)
# Returns 0 if duplicate (already seen), 1 if new
_photo_is_duplicate() {
  local file_id="$1"
  # Use a hash of the file_id as the marker filename (safe for filesystem)
  local marker
  marker="${PHOTO_DEDUP_DIR}/$(printf '%s' "${file_id}" | md5 2>/dev/null || printf '%s' "${file_id}" | md5sum 2>/dev/null | cut -d' ' -f1)"
  if [ -f "${marker}" ]; then
    return 0  # duplicate
  fi
  touch "${marker}"
  return 1  # new
}

# Download a photo from Telegram by file_id, save locally
# Prints the local file path on stdout
# Returns 1 on failure
tg_download_photo() {
  local file_id="$1"

  # Step 1: Get file path from Telegram API
  local file_info
  file_info="$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getFile?file_id=${file_id}" 2>/dev/null)"

  # Extract file_path using grep/sed — no Python
  # Response: {"ok":true,"result":{"file_id":"...","file_unique_id":"...","file_size":12345,"file_path":"photos/file_0.jpg"}}
  local file_path
  file_path="$(printf '%s' "${file_info}" | grep -o '"file_path":"[^"]*"' | head -1 | cut -d'"' -f4)"

  if [ -z "${file_path}" ]; then
    adj_log telegram "getFile failed for file_id=${file_id}"
    return 1
  fi

  # Step 2: Determine extension
  local ext="${file_path##*.}"
  [ -z "${ext}" ] || [ "${ext}" = "${file_path}" ] && ext="jpg"

  # Step 3: Download
  local timestamp
  timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
  local local_path="${PHOTOS_DIR}/${timestamp}_${RANDOM}.${ext}"

  curl -s "https://api.telegram.org/file/bot${TELEGRAM_BOT_TOKEN}/${file_path}" \
    -o "${local_path}" 2>/dev/null

  if [ ! -f "${local_path}" ] || [ ! -s "${local_path}" ]; then
    adj_log telegram "Download failed for ${file_path}"
    rm -f "${local_path}"
    return 1
  fi

  local file_size
  file_size="$(wc -c < "${local_path}" | tr -d ' ')"
  adj_log telegram "Photo saved: ${local_path} (${file_size} bytes)"

  printf '%s' "${local_path}"
}

# Handle an incoming photo message: download, store, run vision, reply
# Args: $1=from_id, $2=message_id, $3=file_id, $4=caption (optional)
tg_handle_photo() {
  local from_id="$1"
  local message_id="$2"
  local file_id="$3"
  local caption="${4:-}"

  # Authorization already checked by dispatch_photo() — no need to duplicate

  adj_log telegram "Photo received msg=${message_id} file_id=${file_id}"

  # Deduplication: skip if this file_id was processed in the last 60 seconds
  _photo_dedup_cleanup
  if _photo_is_duplicate "${file_id}"; then
    adj_log telegram "Skipping duplicate photo file_id=${file_id} (recently processed)"
    return 0
  fi

  msg_react "${message_id}"

  (
    # Disable errexit — this background worker does its own error handling
    set +e

    # Download photo
    local local_path
    local_path="$(tg_download_photo "${file_id}")"

    if [ -z "${local_path}" ] || [ ! -f "${local_path}" ]; then
      msg_send_text "I couldn't retrieve the photo from Telegram. Try again." "${message_id}"
      exit 1
    fi

    # Run vision analysis
    msg_typing start "photo_${message_id}"

    local vision_prompt
    if [ -n "${caption}" ]; then
      vision_prompt="${caption}"
    else
      vision_prompt="Describe what you see in this image. Be concise and informative."
    fi

    local vision_reply
    vision_reply="$(bash "${ADJ_DIR}/scripts/capabilities/vision/vision.sh" "${local_path}" "${vision_prompt}" 2>>"${ADJ_DIR}/state/adjutant.log")"
    local vision_exit=$?

    msg_typing stop "photo_${message_id}"

    if [ ${vision_exit} -ne 0 ] || [ -z "${vision_reply}" ]; then
      msg_send_text "Photo saved to \`${local_path}\` but vision analysis failed. Try again." "${message_id}"
      adj_log telegram "Vision analysis failed for ${local_path}"
    else
      msg_send_text "${vision_reply}" "${message_id}"
      adj_log telegram "Vision reply sent for msg=${message_id}"
    fi
  ) </dev/null >/dev/null 2>&1 &
  disown $!
}
