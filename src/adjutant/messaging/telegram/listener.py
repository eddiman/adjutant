"""Telegram polling loop — main listener entry point.

Replaces: scripts/messaging/telegram/listener.sh

Responsibilities (and nothing else):
  1. Load credentials and check kill state
  2. Acquire single-instance lock (PidLock)
  3. Write own PID into the lock directory
  4. Poll Telegram getUpdates (long-poll, timeout=10s)
  5. Process ALL updates in each batch (sequentially)
  6. Advance offset past ALL updates
  7. Route to dispatch_message / dispatch_photo
  8. Run opencode_reap every 6 cycles (~1 minute)
  9. Release lock and clean up on exit

Run as: python -m adjutant.messaging.telegram.listener
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from adjutant.core.logging import adj_log


_POLL_TIMEOUT = 10  # seconds — long-poll interval passed to Telegram
_REAP_INTERVAL = 6  # poll cycles between opencode_reap calls
_OFFSET_FILE_NAME = "telegram_offset"
_LOCKDIR_NAME = "listener.lock"


def _adj_dir() -> Path:
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise RuntimeError("ADJ_DIR not set.")
    return Path(raw)


def _load_offset(adj_dir: Path) -> int:
    """Read the last persisted offset, or 0 if missing/corrupt."""
    offset_file = adj_dir / "state" / _OFFSET_FILE_NAME
    if offset_file.is_file():
        try:
            raw = offset_file.read_text().strip()
            if raw.isdigit():
                return int(raw)
            else:
                adj_log(
                    "telegram", f"WARNING: corrupt offset file (value: '{raw}'), resetting to 0"
                )
                offset_file.write_text("0\n")
        except OSError:
            pass
    return 0


def _save_offset(adj_dir: Path, offset: int) -> None:
    try:
        (adj_dir / "state" / _OFFSET_FILE_NAME).write_text(str(offset) + "\n")
    except OSError:
        pass


async def _poll_once(
    bot_token: str,
    offset: int,
) -> list[dict] | None:
    """Call getUpdates and return the result list, or None on error."""
    from adjutant.lib.http import get_client

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {
        "offset": offset,
        "timeout": _POLL_TIMEOUT,
        "allowed_updates": '["message"]',
    }
    try:
        client = get_client()
        resp = await asyncio.to_thread(client.get, url, params)
        if not isinstance(resp, dict) or not resp.get("ok"):
            return None
        return resp.get("result") or []
    except Exception as exc:
        adj_log("telegram", f"Poll error: {exc}")
        return None


async def main() -> None:  # noqa: C901 — complexity is inherent to a polling loop
    adj_dir = _adj_dir()
    adj_dir.joinpath("state").mkdir(parents=True, exist_ok=True)

    # --- Pre-flight ---
    from adjutant.core.lockfiles import check_killed, is_killed

    if not check_killed(adj_dir):
        adj_log("telegram", "KILLED lockfile present at startup. Exiting.")
        sys.exit(1)

    from adjutant.core.env import require_telegram_credentials

    try:
        bot_token, chat_id = require_telegram_credentials(adj_dir / ".env")
    except RuntimeError as exc:
        adj_log("telegram", f"Credential error: {exc}")
        sys.exit(1)

    # --- Single-instance guard ---
    from adjutant.core.process import PidLock

    lock = PidLock(adj_dir / "state" / _LOCKDIR_NAME)
    if not lock.acquire():
        held = lock.held_pid
        adj_log("telegram", f"Another listener is already running (PID {held}). Exiting.")
        sys.exit(1)

    adj_log("telegram", f"Lock acquired (PID {os.getpid()})")

    # NOTE: Do NOT set SIGCHLD to SIG_IGN here.  SIG_IGN causes the kernel
    # to auto-reap children before asyncio's _ThreadedChildWatcher can call
    # waitpid(), resulting in returncode 255 for every subprocess.  asyncio
    # already reaps children spawned via create_subprocess_exec.

    # --- State ---
    offset = _load_offset(adj_dir)
    last_processed_id = 0
    reap_counter = 0

    adj_log("telegram", f"Listener started (offset={offset})")

    try:
        while True:
            # Kill-signal check at top of every cycle
            if is_killed(adj_dir):
                adj_log("telegram", "KILLED lockfile detected. Stopping listener.")
                break

            # Periodic opencode reaper
            reap_counter += 1
            if reap_counter >= _REAP_INTERVAL:
                reap_counter = 0
                try:
                    from adjutant.core.opencode import opencode_reap

                    await opencode_reap()
                except Exception as exc:
                    adj_log("telegram", f"opencode_reap error: {exc}")

            # Poll Telegram
            updates = await _poll_once(bot_token, offset)
            if updates is None or len(updates) == 0:
                await asyncio.sleep(1)
                continue

            # Always advance offset past ALL returned updates
            last_update = updates[-1]
            last_update_id: int | None = last_update.get("update_id")
            if last_update_id is not None:
                new_offset = last_update_id + 1
                if new_offset != offset:
                    offset = new_offset
                    _save_offset(adj_dir, offset)

            from adjutant.messaging.dispatch import dispatch_message, dispatch_photo

            # Process ALL updates in the batch sequentially
            skipped = 0
            for update in updates:
                update_id: int | None = update.get("update_id")

                # Deduplicate: skip if we already processed this update_id
                if update_id is not None and update_id <= last_processed_id:
                    skipped += 1
                    continue
                if update_id is not None:
                    last_processed_id = update_id

                message = update.get("message") or {}
                msg_chat_id = (message.get("chat") or {}).get("id")
                message_id = message.get("message_id")

                if not msg_chat_id or not message_id:
                    continue

                # Photo or text?
                photo = message.get("photo")
                if photo:
                    # Highest resolution = last element
                    file_id = photo[-1].get("file_id") if photo else None
                    caption = message.get("caption") or ""
                    if file_id:
                        await dispatch_photo(
                            str(msg_chat_id),
                            message_id,
                            file_id,
                            adj_dir,
                            bot_token=bot_token,
                            chat_id=chat_id,
                            caption=caption,
                        )
                else:
                    text = message.get("text") or ""
                    if text:
                        await dispatch_message(
                            text,
                            message_id,
                            str(msg_chat_id),
                            adj_dir,
                            bot_token=bot_token,
                            chat_id=chat_id,
                        )

            if skipped:
                adj_log(
                    "telegram",
                    f"Skipped {skipped} duplicate update(s) (already processed)",
                )

    finally:
        lock.release()
        adj_log("telegram", "Listener stopped.")


if __name__ == "__main__":
    asyncio.run(main())
