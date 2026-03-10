"""All /command handlers for the Telegram backend.

Replaces: scripts/messaging/telegram/commands.sh

Each handler is an async function with signature:
    cmd_<name>(message_id, adj_dir, *, bot_token, chat_id[, extra_args])

Commands use the send.py primitives (msg_send_text, msg_react, etc.)
rather than calling the Telegram API directly.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from adjutant.core.logging import adj_log


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _journal_append(adj_dir: Path, text: str) -> None:
    """Append a timestamped line to today's journal file."""
    today = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%H:%M %d.%m.%Y")
    journal_path = adj_dir / "journal" / f"{today}.md"
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(journal_path, "a") as f:
            f.write(f"{ts} — {text}\n")
    except OSError:
        pass


def _send(message: str, message_id: int, *, bot_token: str, chat_id: str) -> None:
    """Synchronous shortcut for msg_send_text."""
    from adjutant.messaging.telegram.send import msg_send_text

    msg_send_text(message, message_id, bot_token=bot_token, chat_id=chat_id)


async def _run_opencode_prompt(
    prompt_path: Path,
    timeout: float,
    adj_dir: Path,
    model: str,
) -> str:
    """Run an opencode prompt file and return plain text (max 3800 chars).

    Parses NDJSON output, truncates to 3800 chars, then calls opencode_reap.
    """
    from adjutant.core.opencode import OpenCodeNotFoundError, opencode_reap, opencode_run
    from adjutant.lib.ndjson import parse_ndjson

    if not prompt_path.is_file():
        return f"I can't find the prompt at {prompt_path}."

    prompt_text = prompt_path.read_text()

    args = [
        "run",
        "--agent",
        "adjutant",
        "--dir",
        str(adj_dir),
        "--format",
        "json",
        "--model",
        model,
        prompt_text,
    ]

    try:
        result = await opencode_run(args, timeout=timeout)
    except OpenCodeNotFoundError:
        return "opencode is not available. Please check your installation."
    finally:
        await opencode_reap(adj_dir)

    if result.timed_out:
        return f"The operation timed out after {int(timeout)}s."

    parsed = parse_ndjson(result.stdout)
    reply = parsed.text.strip()

    if not reply and result.returncode != 0:
        return f"The operation ran into an error (exit {result.returncode}). Check adjutant.log for details."

    return reply[:3800]


def _get_model(adj_dir: Path) -> str:
    """Get the current chat model."""
    from adjutant.messaging.telegram.chat import get_model

    return get_model(adj_dir)


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


async def cmd_status(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Report system status."""
    try:
        from adjutant.observability.status import get_status

        status_output = get_status(adj_dir)
    except Exception as exc:
        adj_log("telegram", f"cmd_status error: {exc}")
        status_output = "Could not retrieve status."

    _send(status_output, message_id, bot_token=bot_token, chat_id=chat_id)


# ---------------------------------------------------------------------------
# /pause
# ---------------------------------------------------------------------------


async def cmd_pause(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Pause adjutant."""
    from adjutant.core.lockfiles import set_paused

    set_paused(adj_dir)
    _journal_append(adj_dir, "Paused via Telegram command.")
    _send(
        "Got it, I've paused. Send /resume whenever you want me back.",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    adj_log("telegram", "Adjutant paused via Telegram.")


# ---------------------------------------------------------------------------
# /resume
# ---------------------------------------------------------------------------


async def cmd_resume(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Resume adjutant."""
    from adjutant.core.lockfiles import clear_paused

    clear_paused(adj_dir)
    _journal_append(adj_dir, "Resumed via Telegram command.")
    _send(
        "I'm back online and keeping an eye on things.",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    adj_log("telegram", "Adjutant resumed via Telegram.")


# ---------------------------------------------------------------------------
# /kill
# ---------------------------------------------------------------------------


async def cmd_kill(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Emergency kill switch."""
    adj_log("telegram", "EMERGENCY KILL SWITCH activated via Telegram.")

    # Send reply first so the user gets feedback before the listener stops
    _send(
        "Emergency kill switch activated. Shutting down all systems...",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )

    # Run the kill in a background thread so we return immediately
    def _do_kill() -> None:
        try:
            from adjutant.lifecycle.control import emergency_kill

            emergency_kill(adj_dir)
        except Exception as exc:
            adj_log("telegram", f"emergency_kill error: {exc}")

    t = __import__("threading").Thread(target=_do_kill, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# /pulse
# ---------------------------------------------------------------------------


async def cmd_pulse(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Run a pulse check."""
    import shutil

    _send(
        "On it — running a pulse check now. Give me a moment.",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    adj_log("telegram", "Pulse triggered via Telegram.")

    # No opencode → read heartbeat JSON
    if not shutil.which("opencode"):
        heartbeat_file = adj_dir / "state" / "last_heartbeat.json"
        if not heartbeat_file.is_file():
            _send(
                "I don't have any pulse data yet. Run a pulse from inside OpenCode first and I'll have something to show you.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        try:
            import json

            from adjutant.core.logging import fmt_ts

            data = json.loads(heartbeat_file.read_text())
            raw_ts = data.get("timestamp") or data.get("last_run", "")
            fmt_time = fmt_ts(raw_ts) if raw_ts else ""
            summary = data.get("findings") or data.get("summary") or "Nothing notable recorded."
            time_note = f" ({fmt_time})" if fmt_time else ""
            _send(
                f"Here's what I last recorded{time_note}:\n\n{summary}",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
        except Exception:
            _send(
                "I don't have any pulse data yet.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
        return

    pulse_prompt = adj_dir / "prompts" / "pulse.md"
    model = _get_model(adj_dir)
    result = await _run_opencode_prompt(pulse_prompt, 240.0, adj_dir, model)
    if not result:
        result = "The pulse check completed but returned no output."
    adj_log("telegram", f"Pulse completed via Telegram ({len(result.split())} words).")
    _send(result, message_id, bot_token=bot_token, chat_id=chat_id)


# ---------------------------------------------------------------------------
# /restart
# ---------------------------------------------------------------------------


async def cmd_restart(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Restart all services."""
    _send("Restarting all services...", message_id, bot_token=bot_token, chat_id=chat_id)
    adj_log("telegram", "Restart triggered via Telegram.")

    restart_sh = adj_dir / "scripts" / "lifecycle" / "restart.sh"

    def _do_restart() -> None:
        try:
            subprocess.Popen(
                ["bash", str(restart_sh)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            adj_log("telegram", f"cmd_restart: error spawning restart: {exc}")

    await asyncio.sleep(0.1)  # allow send to complete
    await asyncio.to_thread(_do_restart)

    await asyncio.sleep(2)
    _send(
        "Services restarted. If I don't respond, I'm still restarting — try again in 10 seconds.",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    adj_log("telegram", "Restart completed via Telegram.")


# ---------------------------------------------------------------------------
# /reflect (request) and /confirm (execute)
# ---------------------------------------------------------------------------


async def cmd_reflect_request(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Request a reflection (asks for confirmation)."""
    pending_reflect = adj_dir / "state" / "pending_reflect"
    pending_reflect.parent.mkdir(parents=True, exist_ok=True)
    pending_reflect.touch()
    _send(
        "Starting a full reflection — this goes deeper than a pulse and may take a couple of minutes. "
        "Reply */confirm* if you'd like me to go ahead, or send anything else to cancel.",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    adj_log("telegram", "Reflect requested via Telegram — awaiting confirmation.")


async def cmd_reflect_confirm(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Execute a reflection after confirmation."""
    import shutil

    pending_reflect = adj_dir / "state" / "pending_reflect"
    try:
        pending_reflect.unlink()
    except FileNotFoundError:
        pass

    _send(
        "Great, I'm starting the reflection now — this usually takes a minute or two.",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    adj_log("telegram", "Reflect confirmed via Telegram.")

    if not shutil.which("opencode"):
        _send(
            "I can't find the opencode CLI, so I'm not able to run the reflection from here. "
            "You can trigger it manually with /reflect inside OpenCode.",
            message_id,
            bot_token=bot_token,
            chat_id=chat_id,
        )
        return

    reflect_prompt = adj_dir / "prompts" / "review.md"
    model = _get_model(adj_dir)
    result = await _run_opencode_prompt(reflect_prompt, 300.0, adj_dir, model)
    if not result:
        result = "The reflection completed but returned no output."
    adj_log("telegram", f"Reflect completed via Telegram ({len(result.split())} words).")
    _send(result, message_id, bot_token=bot_token, chat_id=chat_id)


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------


async def cmd_help(
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Show help text."""
    help_text = """\
Here's what I can do for you:

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
/kill — Emergency shutdown. Terminates all Adjutant processes and locks system. Use `adjutant start` to recover.
/help — Shows this message.

You can also send me a photo — I'll store it locally and tell you what I see.\
"""
    _send(help_text, message_id, bot_token=bot_token, chat_id=chat_id)


# ---------------------------------------------------------------------------
# /model [name]
# ---------------------------------------------------------------------------


async def cmd_model(
    arg: str,
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Show or switch the current model."""
    model_file = adj_dir / "state" / "telegram_model.txt"

    current_model = "anthropic/claude-haiku-4-5"
    if model_file.is_file():
        raw = model_file.read_text().strip()
        if raw:
            current_model = raw

    if not arg:
        # Show current + list
        try:
            proc = await asyncio.create_subprocess_exec(
                "opencode",
                "models",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            model_list_lines = stdout.decode(errors="replace").splitlines()[:30]
            model_list = "\n".join(model_list_lines)
        except Exception:
            model_list = "(could not retrieve model list)"

        _send(
            f"Current model: *{current_model}*\n\n"
            f"Available models (first 30 — full list at `opencode models`):\n"
            f"```\n{model_list}\n```\n\n"
            f"Switch with: /model <name>",
            message_id,
            bot_token=bot_token,
            chat_id=chat_id,
        )
        return

    # Validate the new model
    new_model = arg.strip()
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencode",
            "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        available = stdout.decode(errors="replace").splitlines()
        if new_model not in available:
            _send(
                "I don't recognise that model. Run /model to see available options.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return
    except Exception:
        # If we can't verify, allow it (matches bash behaviour — opencode models may fail)
        pass

    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_text(new_model)
    _send(f"Switched to *{new_model}*.", message_id, bot_token=bot_token, chat_id=chat_id)
    adj_log("telegram", f"Model switched to {new_model}")


# ---------------------------------------------------------------------------
# /screenshot <url>
# ---------------------------------------------------------------------------


async def cmd_screenshot(
    url: str,
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Take a screenshot of a URL and send it."""
    from adjutant.messaging.telegram.send import (
        msg_react,
        msg_send_text,
        msg_typing_start,
        msg_typing_stop,
    )

    adj_log("telegram", f"Screenshot requested: {url}")
    msg_react(message_id, "👀", bot_token=bot_token, chat_id=chat_id)

    suffix = f"ss_{message_id}"
    msg_typing_start(suffix, bot_token, chat_id)

    try:
        from adjutant.capabilities.screenshot.screenshot import run_screenshot

        result = await asyncio.to_thread(run_screenshot, url, adj_dir)
    except Exception as exc:
        adj_log("telegram", f"Screenshot error for {url}: {exc}")
        result = f"ERROR:{exc}"

    msg_typing_stop(suffix)

    if result.startswith("ERROR:"):
        err_msg = result[len("ERROR:") :]
        msg_send_text(
            f"Screenshot failed: {err_msg}", message_id, bot_token=bot_token, chat_id=chat_id
        )
        adj_log("telegram", f"Screenshot failed for {url}: {err_msg}")
        return

    # Parse OK:<filepath>:::caption
    payload = result[len("OK:") :]
    if ":::" in payload:
        filepath_str, vision_result = payload.split(":::", 1)
    else:
        filepath_str = payload
        vision_result = ""

    filepath = Path(filepath_str)
    adj_log("telegram", f"Screenshot sent for {url}")

    # Send the photo
    from adjutant.messaging.telegram.send import msg_send_photo

    await asyncio.to_thread(
        msg_send_photo,
        filepath,
        vision_result[:1024] if vision_result else "",
        bot_token=bot_token,
        chat_id=chat_id,
    )

    # Inject into session context (silent)
    try:
        from adjutant.messaging.telegram.chat import run_chat

        session_msg = (
            f"[SCREENSHOT] User requested screenshot of {url}. Vision analysis: {vision_result}"
        )
        await run_chat(session_msg, adj_dir)
    except Exception as exc:
        adj_log("telegram", f"Screenshot session injection failed: {exc}")


# ---------------------------------------------------------------------------
# /search <query>
# ---------------------------------------------------------------------------


async def cmd_search(
    query: str,
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Search the web and send results."""
    from adjutant.messaging.telegram.send import (
        msg_react,
        msg_send_text,
        msg_typing_start,
        msg_typing_stop,
    )

    adj_log("telegram", f"Search requested: {query}")
    msg_react(message_id, "👀", bot_token=bot_token, chat_id=chat_id)

    suffix = f"search_{message_id}"
    msg_typing_start(suffix, bot_token, chat_id)

    try:
        from adjutant.capabilities.search.search import run_search

        result = await asyncio.to_thread(run_search, query, adj_dir)
    except Exception as exc:
        adj_log("telegram", f"Search error for '{query}': {exc}")
        result = f"ERROR:{exc}"

    msg_typing_stop(suffix)

    if result.startswith("ERROR:"):
        err_msg = result[len("ERROR:") :]
        msg_send_text(f"Search failed: {err_msg}", message_id, bot_token=bot_token, chat_id=chat_id)
        adj_log("telegram", f"Search failed for '{query}': {err_msg}")
    else:
        msg_send_text(result[len("OK:") :], message_id, bot_token=bot_token, chat_id=chat_id)
        adj_log("telegram", f"Search results sent for: {query}")


# ---------------------------------------------------------------------------
# /kb [list | query <name> <question>]
# ---------------------------------------------------------------------------


async def cmd_kb(
    action_str: str,
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """List or query knowledge bases."""
    from adjutant.capabilities.kb.manage import kb_count, kb_exists, kb_list
    from adjutant.messaging.telegram.send import (
        msg_react,
        msg_send_text,
        msg_typing_start,
        msg_typing_stop,
    )

    parts = action_str.split() if action_str.strip() else []
    action = parts[0] if parts else "list"

    if action in ("", "list"):
        count = kb_count(adj_dir)
        if count == 0:
            _send(
                "No knowledge bases registered yet. Create one with `adjutant kb create`.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        entries = kb_list(adj_dir)
        lines = [f"*Knowledge Bases* ({count}):"]
        for e in entries:
            lines.append(f"\n• *{e.name}* ({e.access}) — {e.description}")
        lines.append("\n\nQuery with: /kb query <name> <question>")
        _send("".join(lines), message_id, bot_token=bot_token, chat_id=chat_id)
        return

    if action == "query":
        # /kb query <name> <question...>
        if len(parts) < 3:
            _send(
                "Usage: /kb query <name> <your question>",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        kb_name = parts[1]
        query = " ".join(parts[2:])

        if not kb_exists(adj_dir, kb_name):
            _send(
                f"Knowledge base '{kb_name}' not found. Run /kb list to see available KBs.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        msg_react(message_id, "👀", bot_token=bot_token, chat_id=chat_id)

        suffix = f"kb_{message_id}"
        msg_typing_start(suffix, bot_token, chat_id)

        try:
            from adjutant.capabilities.kb.query import kb_query

            result = await kb_query(kb_name, query, adj_dir)
        except Exception as exc:
            adj_log("telegram", f"KB query error for {kb_name}: {exc}")
            result = ""

        msg_typing_stop(suffix)

        if not result:
            msg_send_text(
                "KB query failed or returned empty. Check the KB has content.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            adj_log("telegram", f"KB query failed for {kb_name}: {query}")
        else:
            msg_send_text(f"[{kb_name}] {result}", message_id, bot_token=bot_token, chat_id=chat_id)
            adj_log("telegram", f"KB query answered from {kb_name}")
        return

    # Unknown action
    _send(
        "Usage: /kb list — show knowledge bases\n/kb query <name> <question> — ask a KB",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )


# ---------------------------------------------------------------------------
# /schedule [list | run <name> | enable <name> | disable <name>]
# ---------------------------------------------------------------------------


async def cmd_schedule(
    input_str: str,
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """List or manage scheduled jobs."""
    from adjutant.capabilities.schedule.manage import (
        schedule_count,
        schedule_exists,
        schedule_get_field,
        schedule_list,
        schedule_set_enabled,
    )
    from adjutant.messaging.telegram.send import (
        msg_react,
        msg_send_text,
        msg_typing_start,
        msg_typing_stop,
    )

    config_path = adj_dir / "adjutant.yaml"
    parts = input_str.split() if input_str.strip() else []
    action = parts[0] if parts else "list"
    name = parts[1] if len(parts) > 1 else ""

    if action in ("", "list"):
        count = schedule_count(config_path)
        if count == 0:
            _send(
                "No scheduled jobs registered yet. Add one with `adjutant schedule add`.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        jobs = schedule_list(config_path)
        lines = [f"*Scheduled Jobs* ({count}):"]
        for job in jobs:
            jname = job.get("name", "?")
            desc = job.get("description", "")
            sched = job.get("schedule", "")
            enabled = job.get("enabled", True)
            flag = "" if enabled else " _(disabled)_"
            lines.append(f"\n• *{jname}*{flag} — {sched}\n  {desc}")
        lines.append(
            "\n\nManage: /schedule run <name> | /schedule enable <name> | /schedule disable <name>"
        )
        _send("".join(lines), message_id, bot_token=bot_token, chat_id=chat_id)
        return

    if action == "run":
        if not name:
            _send("Usage: /schedule run <name>", message_id, bot_token=bot_token, chat_id=chat_id)
            return
        if not schedule_exists(config_path, name):
            _send(
                f"Job '{name}' not found. Use /schedule list to see registered jobs.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return

        msg_react(message_id, "👀", bot_token=bot_token, chat_id=chat_id)

        suffix = f"sched_{message_id}"
        msg_typing_start(suffix, bot_token, chat_id)

        try:
            script_raw = schedule_get_field(config_path, name, "script")
            if script_raw.startswith("/"):
                script_path = script_raw
            else:
                script_path = str(adj_dir / script_raw)

            proc = await asyncio.create_subprocess_exec(
                "bash",
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            run_exit = proc.returncode or 0
            result = stdout_b.decode(errors="replace").strip()
        except Exception as exc:
            adj_log("telegram", f"Schedule run error for '{name}': {exc}")
            result = ""
            run_exit = 1

        msg_typing_stop(suffix)

        if run_exit != 0 or not result:
            msg_send_text(
                f"[{name}] Job completed (exit {run_exit}).",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
        else:
            msg_send_text(f"[{name}] {result}", message_id, bot_token=bot_token, chat_id=chat_id)
        adj_log("telegram", f"Schedule job '{name}' run via Telegram (exit {run_exit})")
        return

    if action == "enable":
        if not name:
            _send(
                "Usage: /schedule enable <name>", message_id, bot_token=bot_token, chat_id=chat_id
            )
            return
        if not schedule_exists(config_path, name):
            _send(
                f"Job '{name}' not found. Use /schedule list to see registered jobs.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return
        try:
            schedule_set_enabled(config_path, name, True, adj_dir)
        except Exception as exc:
            adj_log("telegram", f"schedule enable error: {exc}")
        _send(
            f"Job *{name}* enabled — crontab entry installed.",
            message_id,
            bot_token=bot_token,
            chat_id=chat_id,
        )
        adj_log("telegram", f"Schedule job '{name}' enabled via Telegram")
        return

    if action == "disable":
        if not name:
            _send(
                "Usage: /schedule disable <name>", message_id, bot_token=bot_token, chat_id=chat_id
            )
            return
        if not schedule_exists(config_path, name):
            _send(
                f"Job '{name}' not found. Use /schedule list to see registered jobs.",
                message_id,
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return
        try:
            schedule_set_enabled(config_path, name, False, adj_dir)
        except Exception as exc:
            adj_log("telegram", f"schedule disable error: {exc}")
        _send(
            f"Job *{name}* disabled — crontab entry removed.",
            message_id,
            bot_token=bot_token,
            chat_id=chat_id,
        )
        adj_log("telegram", f"Schedule job '{name}' disabled via Telegram")
        return

    # Unknown subcommand
    _send(
        "Usage:\n"
        "/schedule list — show all scheduled jobs\n"
        "/schedule run <name> — run a job immediately\n"
        "/schedule enable <name> — enable a job\n"
        "/schedule disable <name> — disable a job",
        message_id,
        bot_token=bot_token,
        chat_id=chat_id,
    )
