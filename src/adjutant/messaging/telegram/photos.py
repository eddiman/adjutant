"""Telegram photo download, deduplication, and vision routing.

Replaces: scripts/messaging/telegram/photos.sh

Provides:
  tg_download_photo  — download a Telegram photo by file_id to adj_dir/photos/
  tg_handle_photo    — async orchestrator: dedup → download → vision → reply
"""

from __future__ import annotations

import hashlib
import random
import time
from datetime import datetime
from pathlib import Path

from adjutant.core.logging import adj_log


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------


def _photo_dedup_cleanup(dedup_dir: Path) -> None:
    """Remove marker files older than 60 seconds.

    Matches bash: find <dir> -type f -mmin +1 -delete
    """
    cutoff = time.time() - 60.0
    try:
        for marker in dedup_dir.iterdir():
            if marker.is_file() and marker.stat().st_mtime < cutoff:
                try:
                    marker.unlink()
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def _photo_is_duplicate(file_id: str, dedup_dir: Path) -> bool:
    """Check if file_id was processed in the last 60 seconds.

    Uses md5 hash of file_id as the marker filename (safe for filesystem).

    Returns:
        True if duplicate (already seen), False if new.
    """
    dedup_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(file_id.encode()).hexdigest()
    marker = dedup_dir / digest
    if marker.exists():
        return True
    marker.touch()
    return False


# ---------------------------------------------------------------------------
# Photo download
# ---------------------------------------------------------------------------


def tg_download_photo(
    file_id: str,
    *,
    bot_token: str,
    adj_dir: Path,
) -> Path | None:
    """Download a Telegram photo by file_id and save to adj_dir/photos/.

    Calls getFile API to get the file path, then downloads the binary.

    Args:
        file_id: Telegram file_id from the photo message.
        bot_token: Telegram bot token.
        adj_dir: Adjutant root directory.

    Returns:
        Path to the saved local file, or None on failure.
    """
    from adjutant.lib.http import get_client

    photos_dir = adj_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)

    client = get_client()

    # Step 1: Get file path from Telegram
    try:
        resp = client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
        )
    except Exception as exc:
        adj_log("telegram", f"getFile failed for file_id={file_id}: {exc}")
        return None

    if not resp.get("ok"):
        adj_log("telegram", f"getFile returned ok=false for file_id={file_id}")
        return None

    file_path_str: str = resp.get("result", {}).get("file_path", "")
    if not file_path_str:
        adj_log("telegram", f"getFile returned no file_path for file_id={file_id}")
        return None

    # Step 2: Determine extension
    ext = file_path_str.rsplit(".", 1)[-1] if "." in file_path_str else "jpg"
    if not ext or ext == file_path_str:
        ext = "jpg"

    # Step 3: Download binary
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    rnd = random.randint(1000, 9999)
    local_path = photos_dir / f"{timestamp}_{rnd}.{ext}"

    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_str}"
    try:
        import httpx

        with httpx.Client(timeout=30.0) as http:
            response = http.get(download_url)
            response.raise_for_status()
            local_path.write_bytes(response.content)
    except Exception as exc:
        adj_log("telegram", f"Download failed for {file_path_str}: {exc}")
        try:
            local_path.unlink()
        except FileNotFoundError:
            pass
        return None

    if not local_path.exists() or local_path.stat().st_size == 0:
        adj_log("telegram", f"Downloaded file is empty: {local_path}")
        try:
            local_path.unlink()
        except FileNotFoundError:
            pass
        return None

    file_size = local_path.stat().st_size
    adj_log("telegram", f"Photo saved: {local_path} ({file_size} bytes)")
    return local_path


# ---------------------------------------------------------------------------
# Photo handler
# ---------------------------------------------------------------------------


async def tg_handle_photo(
    from_id: str,
    message_id: int,
    file_id: str,
    caption: str,
    *,
    bot_token: str,
    chat_id: str,
    adj_dir: Path,
) -> None:
    """Handle an incoming Telegram photo: dedup → download → vision → reply.

    Authorization is expected to have been checked by the caller (dispatcher).

    Args:
        from_id: Sender chat ID (used for logging).
        message_id: Telegram message ID.
        file_id: Telegram file_id of the highest-resolution photo.
        caption: Optional caption text sent with the photo.
        bot_token: Telegram bot token.
        chat_id: Target chat ID for sending replies.
        adj_dir: Adjutant root directory.
    """
    import asyncio

    from adjutant.messaging.telegram.send import (
        msg_react,
        msg_send_text,
        msg_typing_start,
        msg_typing_stop,
    )

    adj_log("telegram", f"Photo received msg={message_id} file_id={file_id}")

    # Deduplication
    dedup_dir = adj_dir / "state" / "photo_dedup"
    _photo_dedup_cleanup(dedup_dir)
    if _photo_is_duplicate(file_id, dedup_dir):
        adj_log("telegram", f"Skipping duplicate photo file_id={file_id} (recently processed)")
        return

    # React immediately
    msg_react(message_id, "👀", bot_token=bot_token, chat_id=chat_id)

    # Run the rest in a background task so the listener loop can continue
    async def _background() -> None:
        # Download photo
        local_path = await asyncio.to_thread(
            tg_download_photo,
            file_id,
            bot_token=bot_token,
            adj_dir=adj_dir,
        )

        if local_path is None or not local_path.exists():
            msg_send_text(
                "I couldn't retrieve the photo from Telegram. Try again.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        # Run vision analysis
        suffix = f"photo_{message_id}"
        msg_typing_start(suffix, bot_token, chat_id)

        vision_prompt = (
            caption
            if caption
            else "Describe what you see in this image. Be concise and informative."
        )

        try:
            from adjutant.capabilities.vision.vision import run_vision

            vision_reply = await asyncio.to_thread(
                run_vision, str(local_path), vision_prompt, adj_dir
            )
        except Exception as exc:
            adj_log("telegram", f"Vision analysis error for {local_path}: {exc}")
            vision_reply = ""
        finally:
            msg_typing_stop(suffix)

        if not vision_reply:
            msg_send_text(
                f"Photo saved to `{local_path}` but vision analysis failed. Try again.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            adj_log("telegram", f"Vision analysis failed for {local_path}")
            return

        msg_send_text(vision_reply, message_id, bot_token=bot_token, chat_id=chat_id)
        adj_log("telegram", f"Vision reply sent for msg={message_id}")

        # Inject into session context (silent — errors ignored)
        try:
            caption_note = f' with caption: "{caption}"' if caption else ""
            session_msg = (
                f"[PHOTO] User sent a photo{caption_note}. Vision analysis: {vision_reply}"
            )
            from adjutant.messaging.telegram.chat import run_chat

            await run_chat(session_msg, adj_dir)
        except Exception as exc:
            adj_log("telegram", f"Session injection failed: {exc}")

    asyncio.create_task(_background())
