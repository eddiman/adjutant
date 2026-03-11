"""Website screenshot capture and Telegram delivery.

Replaces: scripts/capabilities/screenshot/screenshot.sh

Strategy:
  1. Validate and normalise URL (add https:// if missing)
  2. Take a 1280×900 viewport screenshot via Node.js Playwright script
  3. Generate a caption via vision.py if none provided (max 1024 chars)
  4. Try sendPhoto first (fits Telegram's dimension limits)
  5. Fall back to sendDocument (no dimension limits, up to 50 MB)

Output: prints "OK:<filepath>:::caption" or "ERROR:<reason>" to stdout.

The Node.js playwright_screenshot.mjs script stays as-is — this module
calls it via subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


_TELEGRAM_CAPTION_MAX = 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_url(url: str) -> str:
    """Add https:// prefix if missing."""
    if not url.startswith("http://") and not url.startswith("https://"):
        return "https://" + url
    return url


def _domain_from_url(url: str) -> str:
    """Extract a filesystem-safe domain name for the output filename."""
    try:
        netloc = urlparse(url).netloc
        domain = netloc.replace("www.", "").replace(":", "-")
        return domain[:40] if domain else "page"
    except Exception:
        return "page"


def _take_screenshot(url: str, outfile: Path) -> tuple[bool, str]:
    """Run playwright_screenshot.mjs and return (success, error_message)."""
    pw_script = Path(__file__).parent / "playwright_screenshot.mjs"
    if not pw_script.is_file():
        return False, f"playwright_screenshot.mjs not found at {pw_script}"

    result = subprocess.run(
        ["node", str(pw_script), url, str(outfile)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not outfile.is_file():
        err = (result.stderr or result.stdout or "unknown error").strip()
        # Take the last 3 lines, matching bash `tail -3`
        last_lines = "\n".join(err.splitlines()[-3:])
        return False, last_lines

    return True, ""


def _generate_vision_caption(outfile: Path, adj_dir: Path) -> str:
    """Generate a caption for the screenshot using vision.py."""
    prompt = (
        "Analyze this webpage screenshot. There may be a cookie consent banner, "
        "GDPR prompt, or other overlay in the foreground — ignore it and focus on "
        "the underlying page content behind it. Describe what the page is about in "
        "1-3 concise sentences: the site name, main topic or purpose, and any key "
        "visible content (headlines, products, data, etc.). Be specific and factual."
    )
    try:
        from adjutant.capabilities.vision.vision import run_vision

        result = run_vision(str(outfile), prompt, adj_dir)
        return result.strip()
    except Exception:
        return ""


def _send_photo(bot_token: str, chat_id: str, outfile: Path, caption: str) -> tuple[bool, str]:
    """Try Telegram sendPhoto. Returns (ok, error_description)."""
    import httpx

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(outfile, "rb") as f:
            resp = httpx.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("screenshot.png", f, "image/png")},
                timeout=30.0,
            )
        data = resp.json()
        if data.get("ok"):
            return True, ""
        return False, data.get("description", "unknown")
    except Exception as e:
        return False, str(e)


def _send_document(bot_token: str, chat_id: str, outfile: Path, caption: str) -> tuple[bool, str]:
    """Fallback to Telegram sendDocument. Returns (ok, error_description)."""
    import httpx

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        with open(outfile, "rb") as f:
            resp = httpx.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": ("screenshot.png", f, "image/png")},
                timeout=60.0,
            )
        data = resp.json()
        if data.get("ok"):
            return True, ""
        return False, data.get("description", "unknown")
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def take_and_send(
    url: str,
    adj_dir: Path,
    caption: str = "",
    *,
    env_path: Path | None = None,
) -> str:
    """Take a screenshot and send it to Telegram.

    Args:
        url: URL to screenshot (https:// added if missing).
        adj_dir: Adjutant root directory.
        caption: Optional caption override. If empty, generated via vision.
        env_path: Override .env path (for testing).

    Returns:
        "OK:<filepath>:::caption" on success.
        "ERROR:<reason>" on failure.
    """
    from adjutant.core.env import require_telegram_credentials
    from adjutant.core.logging import adj_log

    if not url:
        return "ERROR: No URL provided."

    url = _normalise_url(url)

    # Load credentials
    try:
        bot_token, chat_id = require_telegram_credentials(env_path or (adj_dir / ".env"))
    except RuntimeError as e:
        return f"ERROR: Missing bot credentials — {e}"

    # Build output filename
    screenshots_dir = adj_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    domain = _domain_from_url(url)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outfile = screenshots_dir / f"{timestamp}_{domain}.png"

    adj_log("screenshot", f"Screenshot requested: {url}")

    # Take screenshot
    ok, err = _take_screenshot(url, outfile)
    if not ok:
        adj_log("screenshot", f"Screenshot FAILED for {url}: {err}")
        return f"ERROR: Screenshot failed — {err}"

    file_size = outfile.stat().st_size
    adj_log("screenshot", f"Screenshot saved: {outfile} ({file_size} bytes)")

    # Generate caption via vision if not provided
    if not caption:
        adj_log("screenshot", f"Running vision analysis on {outfile}")
        vision_caption = _generate_vision_caption(outfile, adj_dir)
        if vision_caption:
            caption = vision_caption
            adj_log("screenshot", f"Vision caption generated for {url}")
        else:
            adj_log("screenshot", "Vision returned empty — falling back to URL caption")
            caption = url

    # Clamp caption to 1024 chars
    caption = caption[:_TELEGRAM_CAPTION_MAX]

    # Try sendPhoto first
    ok, tg_err = _send_photo(bot_token, chat_id, outfile, caption)
    if ok:
        adj_log("screenshot", f"Screenshot sent via sendPhoto for {url}")
        return f"OK:{outfile}:::{caption}"

    adj_log("screenshot", f"sendPhoto failed ({tg_err}), falling back to sendDocument")

    # Fallback: sendDocument
    ok2, tg_err2 = _send_document(bot_token, chat_id, outfile, caption)
    if ok2:
        adj_log("screenshot", f"Screenshot sent via sendDocument for {url}")
        return f"OK:{outfile}:::{caption}"

    adj_log("screenshot", f"sendDocument also failed for {url}: {tg_err2}")
    return f"ERROR: Could not send screenshot — sendPhoto: {tg_err}, sendDocument: {tg_err2}"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: screenshot.py <url> [caption]"""
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        sys.stderr.write("Usage: screenshot.py <url> [caption]\n")
        return 1

    url = args[0]
    caption = args[1] if len(args) > 1 else ""

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)
    result = take_and_send(url, adj_dir, caption)
    print(result)
    return 0 if result.startswith("OK:") else 1


# Alias used by commands.py
run_screenshot = take_and_send


if __name__ == "__main__":
    sys.exit(main())
