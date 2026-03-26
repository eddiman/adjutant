"""
Adjutant Web Notes Filter for Open WebUI v0.7.2+
- Slash commands: /notes, /read, /new, /search
- Auto-fetch note-X mentions
- HTML cards with action buttons via event emitter
- Compact expandable lists
"""

import re
import json
import requests
from pydantic import BaseModel, Field
from typing import Optional, Callable, Awaitable


class Filter:
    class Valves(BaseModel):
        adjutant_web_url: str = Field(
            default="http://host.docker.internal:3020",
            description="Adjutant Web API URL"
        )
        enable_auto_fetch: bool = Field(
            default=True,
            description="Auto-fetch notes when mentioned (e.g., note-5)"
        )
        enable_slash_commands: bool = Field(
            default=True,
            description="Enable /notes, /read, /new, /search commands"
        )

    def __init__(self):
        self.valves = self.Valves()

    # --- API Helpers ---

    def api_get(self, endpoint: str) -> Optional[dict]:
        try:
            r = requests.get(f"{self.valves.adjutant_web_url}{endpoint}", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def api_post(self, endpoint: str, data: dict) -> Optional[dict]:
        try:
            r = requests.post(f"{self.valves.adjutant_web_url}{endpoint}", json=data, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def api_delete(self, endpoint: str) -> bool:
        try:
            r = requests.delete(f"{self.valves.adjutant_web_url}{endpoint}", timeout=5)
            return r.status_code == 204
        except Exception:
            return False

    def fetch_note(self, slug: str) -> Optional[dict]:
        return self.api_get(f"/api/notes/{slug}")

    def fetch_notes(self, params: Optional[dict] = None) -> list:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items() if v)
        data = self.api_get(f"/api/notes{query}")
        return data.get("notes", []) if data else []

    def fetch_categories(self) -> list:
        data = self.api_get("/api/categories")
        return data.get("categories", []) if data else []

    def fetch_tags(self) -> list:
        data = self.api_get("/api/tags")
        return data.get("tags", []) if data else []

    # --- Markdown Rendering (works reliably in OWUI) ---

    def render_note_md(self, note: dict, compact: bool = False) -> str:
        title = note.get("title", "Untitled")
        slug = note.get("slug", "")
        category = note.get("category", "uncategorized")
        tags = note.get("tags", [])
        content = note.get("content", "")
        updated = note.get("updatedAt", "")

        tags_str = ", ".join(f"`{t}`" for t in tags) if tags else "_no tags_"

        if compact:
            return f"**{title}** ({slug}) — _{category}_ · {len(tags)} tags"

        return f"""### {title}

**Category:** {category} | **Tags:** {tags_str}  
**Slug:** `{slug}` | **Updated:** {updated}

---

{content if content else "_No content_"}

---

**Actions:** `read {slug}` · `edit {slug}` · `delete {slug}`
"""

    def render_notes_list_md(self, notes: list) -> str:
        if not notes:
            return "⚠️ **No notes found.** Use `/new` to create one."

        lines = [f"### Your Notes ({len(notes)} total)\n"]
        for n in notes:
            title = n.get("title", "Untitled")
            slug = n.get("slug", "")
            category = n.get("category", "")
            tags = n.get("tags", [])
            tags_str = f"[{', '.join(tags)}]" if tags else ""
            lines.append(f"- **{title}** `{slug}` — _{category}_ {tags_str}")

        lines.append("\n_Say `read <slug>` to view a note._")
        return "\n".join(lines)

    def render_error_md(self, title: str, message: str) -> str:
        return f"⚠️ **{title}**\n\n{message}"

    def render_creation_form(self) -> str:
        categories = self.fetch_categories()
        tags = self.fetch_tags()
        cats_str = ", ".join(f"`{c}`" for c in categories) if categories else "`uncategorized`"
        tags_str = ", ".join(f"`{t}`" for t in tags) if tags else "_none yet_"

        return f"""I'd like to create a new note. Please help me fill in:

📝 **Title:** [required]  
📁 **Category:** {cats_str}  
🏷️ **Tags:** {tags_str}  
📄 **Content:** [what should the note contain?]

_Guide me through each field one at a time._"""

    # --- Main Filters ---

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None
    ) -> dict:
        messages = body.get("messages", [])
        if not messages:
            return body

        last_msg = messages[-1].get("content", "")
        if not isinstance(last_msg, str):
            return body

        original_msg = last_msg.strip()

        # Helper to emit message
        async def emit_message(content: str, done: bool = True):
            if __event_emitter__:
                await __event_emitter__({
                    "type": "message",
                    "data": {"content": content}
                })

        async def emit_status(description: str, done: bool = True):
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": description, "done": done}
                })

        # --- Slash Commands ---
        if self.valves.enable_slash_commands:

            # Normalize: lowercase, strip extra whitespace
            cmd = original_msg.lower().strip()

            # /notes - list all
            if cmd == "/notes" or cmd == "notes" or cmd.startswith("/notes "):
                await emit_status("Fetching notes...", done=False)
                notes = self.fetch_notes()
                md = self.render_notes_list_md(notes)
                await emit_status("Notes loaded", done=True)
                # Replace message to tell LLM context
                messages[-1]["content"] = f"[User requested note list. Display this to them:]\n\n{md}"
                return body

            # /read note-X
            match = re.match(r"/?read\s+(note-\d+)", cmd, re.IGNORECASE)
            if match:
                slug = match.group(1)
                await emit_status(f"Fetching {slug}...", done=False)
                note = self.fetch_note(slug)
                if note:
                    md = self.render_note_md(note, compact=False)
                    await emit_status("Note loaded", done=True)
                    messages[-1]["content"] = f"[User requested to read {slug}. Display this:]\n\n{md}"
                else:
                    md = self.render_error_md("Note not found", f"Could not find `{slug}`.")
                    await emit_status("Not found", done=True)
                    messages[-1]["content"] = f"[Error: note not found]\n\n{md}"
                return body

            # /new - create note
            if cmd == "/new" or cmd == "new":
                form = self.render_creation_form()
                messages[-1]["content"] = form
                return body

            # /search <query>
            match = re.match(r"/?search\s+(.+)", cmd, re.IGNORECASE)
            if match:
                query = match.group(1)
                await emit_status(f"Searching for '{query}'...", done=False)
                notes = self.fetch_notes({"search": query})
                if notes:
                    md = self.render_notes_list_md(notes)
                    await emit_status(f"Found {len(notes)} notes", done=True)
                else:
                    md = self.render_error_md("No results", f"No notes found matching '{query}'.")
                    await emit_status("No results", done=True)
                messages[-1]["content"] = f"[Search results for '{query}':]\n\n{md}"
                return body

        # --- Auto-fetch note mentions ---
        if self.valves.enable_auto_fetch:
            slugs = list(set(re.findall(r"note-\d+", original_msg, re.IGNORECASE)))
            if slugs:
                context_parts = []
                for slug in slugs:
                    note = self.fetch_note(slug)
                    if note:
                        context_parts.append(
                            f"**{note.get('title')}** (`{slug}`)\n"
                            f"Category: {note.get('category')} | Tags: {', '.join(note.get('tags', []))}\n"
                            f"Content: {note.get('content', '(empty)')}\n"
                        )

                if context_parts:
                    context = "\n---\n".join(context_parts)
                    messages[-1]["content"] = f"[Context: Referenced notes]\n\n{context}\n\n[User message:] {original_msg}"

        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # Outlet: post-process LLM responses
        # For now, we let the LLM response pass through
        # The inlet already provides formatted markdown that renders well
        return body
