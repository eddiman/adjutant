"""
Adjutant Web Notes Pipe for Open WebUI v0.7.2+
- Direct HTML rendering for /notes, /read, /search
- Bypasses LLM for fast display
- Natural language passes through to LLM + MCP
"""

import re
import requests
from pydantic import BaseModel, Field
from typing import Optional, Union, Generator, Iterator


class Pipe:
    class Valves(BaseModel):
        adjutant_web_url: str = Field(
            default="http://host.docker.internal:3020",
            description="Adjutant Web API URL"
        )
        passthrough_model: str = Field(
            default="",
            description="Model ID to use for non-command messages (leave empty to use default)"
        )

    def __init__(self):
        self.valves = self.Valves()
        self.name = "Adjutant Web Notes"

    # --- API Helpers ---

    def api_get(self, endpoint: str) -> Optional[dict]:
        try:
            r = requests.get(f"{self.valves.adjutant_web_url}{endpoint}", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def api_delete(self, endpoint: str) -> dict:
        try:
            r = requests.delete(f"{self.valves.adjutant_web_url}{endpoint}", timeout=5)
            if r.status_code == 204:
                return {"success": True}
            return {"error": f"Status {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def fetch_note(self, slug: str) -> Optional[dict]:
        return self.api_get(f"/api/notes/{slug}")

    def fetch_notes(self, params: Optional[dict] = None) -> dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items() if v)
        return self.api_get(f"/api/notes{query}")

    def fetch_categories(self) -> list:
        data = self.api_get("/api/categories")
        if data and "categories" in data:
            return data["categories"]
        return []

    def fetch_tags(self) -> list:
        data = self.api_get("/api/tags")
        if data and "tags" in data:
            return data["tags"]
        return []

    # --- HTML Rendering ---

    def css_styles(self) -> str:
        return """
<style>
.note-card {
    border: 1px solid #444;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    background: #1e1e1e;
    font-family: system-ui, -apple-system, sans-serif;
}
.note-card-light {
    background: #f8f8f8;
    border-color: #ddd;
}
.note-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}
.note-title {
    font-size: 18px;
    font-weight: 600;
    color: #e0e0e0;
    margin: 0;
}
.note-card-light .note-title {
    color: #222;
}
.note-category {
    background: #333;
    color: #aaa;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
}
.note-card-light .note-category {
    background: #e0e0e0;
    color: #555;
}
.note-tags {
    margin-bottom: 12px;
}
.note-tag {
    background: #2a4a2a;
    color: #8f8;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    margin-right: 6px;
    display: inline-block;
}
.note-card-light .note-tag {
    background: #d4edda;
    color: #155724;
}
.note-meta {
    color: #888;
    font-size: 12px;
    margin-bottom: 12px;
}
.note-content {
    background: #252525;
    padding: 12px;
    border-radius: 6px;
    color: #ccc;
    font-size: 14px;
    white-space: pre-wrap;
    line-height: 1.5;
}
.note-card-light .note-content {
    background: #fff;
    color: #333;
    border: 1px solid #e0e0e0;
}
.note-actions {
    margin-top: 14px;
    display: flex;
    gap: 8px;
}
.note-btn {
    padding: 8px 14px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
}
.note-btn-read {
    background: #2a4a2a;
    color: #8f8;
}
.note-btn-edit {
    background: #4a4a2a;
    color: #ff8;
}
.note-btn-delete {
    background: #4a2a2a;
    color: #f88;
}
.note-list-item {
    border: 1px solid #333;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 6px 0;
    background: #1a1a1a;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.note-card-light .note-list-item {
    background: #fff;
    border-color: #ddd;
}
.note-list-title {
    font-weight: 500;
    color: #e0e0e0;
}
.note-card-light .note-list-title {
    color: #222;
}
.note-list-meta {
    color: #666;
    font-size: 12px;
}
.note-error {
    border: 1px solid #a33;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    background: #2a1a1a;
}
.note-error-title {
    color: #f66;
    font-weight: 600;
    margin-bottom: 6px;
}
.note-error-msg {
    color: #a88;
    font-size: 14px;
}
.note-help {
    color: #888;
    font-size: 13px;
    margin-top: 12px;
    padding: 10px;
    background: #252525;
    border-radius: 6px;
}
.note-card-light .note-help {
    background: #f0f0f0;
}
</style>
"""

    def render_note_card(self, note: dict) -> str:
        title = note.get("title", "Untitled")
        slug = note.get("slug", "")
        category = note.get("category", "uncategorized")
        tags = note.get("tags", [])
        content = note.get("content", "")
        updated = note.get("updatedAt", "")

        tags_html = "".join(f'<span class="note-tag">{t}</span>' for t in tags) if tags else '<span style="color:#666;font-size:12px;">no tags</span>'

        return f"""
<div class="note-card">
    <div class="note-header">
        <h3 class="note-title">{title}</h3>
        <span class="note-category">{category}</span>
    </div>
    <div class="note-tags">{tags_html}</div>
    <div class="note-meta">
        <strong>Slug:</strong> {slug} &nbsp;|&nbsp; <strong>Updated:</strong> {updated}
    </div>
    <div class="note-content">{content if content else "(empty)"}</div>
    <div class="note-help">
        💡 To modify: <code>change title to "..."</code> · <code>add tag "..."</code> · <code>update content to "..."</code>
    </div>
</div>
"""

    def render_note_list(self, notes: list) -> str:
        if not notes:
            return self.render_error("No notes found", "You don't have any notes yet. Say <code>create note titled \"...\"</code> to make one.")

        items = []
        for n in notes:
            title = n.get("title", "Untitled")
            slug = n.get("slug", "")
            category = n.get("category", "")
            tag_count = len(n.get("tags", []))
            items.append(f"""
<div class="note-list-item">
    <span class="note-list-title">{title}</span>
    <span class="note-list-meta">{category} · {tag_count} tags · <code>{slug}</code></span>
</div>
""")

        return f"""
<div class="note-card">
    <h3 class="note-title">Your Notes ({len(notes)})</h3>
    <div style="margin-top:12px;">
        {"".join(items)}
    </div>
    <div class="note-help">
        💡 Say <code>read note-X</code> to view a note · <code>search "..."</code> to filter
    </div>
</div>
"""

    def render_error(self, title: str, message: str) -> str:
        return f"""
<div class="note-error">
    <div class="note-error-title">⚠️ {title}</div>
    <div class="note-error-msg">{message}</div>
</div>
"""

    def render_help(self) -> str:
        return """
<div class="note-card">
    <h3 class="note-title">Adjutant Web Notes - Help</h3>
    <div class="note-content">
<strong>Commands:</strong>
• <code>notes</code> or <code>/notes</code> — List all notes
• <code>read note-X</code> — View a specific note
• <code>search "query"</code> — Find notes by title/content
• <code>categories</code> — List all categories
• <code>tags</code> — List all tags

<strong>Creating & Editing:</strong>
• <code>create note titled "..."</code> — Create new note
• <code>delete note-X</code> — Delete a note

After viewing a note, you can ask me to:
• Change the title, content, category, or tags
• Summarize or expand the content
• Move it to a different category
    </div>
</div>
"""

    def render_categories(self, categories: list) -> str:
        if not categories:
            return self.render_error("No categories", "No categories found.")
        
        items = "".join(f'<span class="note-tag" style="margin:4px;">{c}</span>' for c in categories)
        return f"""
<div class="note-card">
    <h3 class="note-title">Categories</h3>
    <div style="margin-top:12px;">{items}</div>
</div>
"""

    def render_tags_list(self, tags: list) -> str:
        if not tags:
            return self.render_error("No tags", "No tags found.")
        
        items = "".join(f'<span class="note-tag" style="margin:4px;">{t}</span>' for t in tags)
        return f"""
<div class="note-card">
    <h3 class="note-title">All Tags</h3>
    <div style="margin-top:12px;">{items}</div>
</div>
"""

    def render_deleted(self, slug: str) -> str:
        return f"""
<div class="note-card" style="border-color:#4a4;">
    <h3 class="note-title" style="color:#8f8;">✓ Note Deleted</h3>
    <div class="note-meta">Successfully deleted <code>{slug}</code></div>
</div>
"""

    # --- Main Pipe ---

    def pipe(self, body: dict) -> Union[str, Generator, Iterator]:
        messages = body.get("messages", [])
        if not messages:
            return "No messages received."

        user_msg = messages[-1].get("content", "").strip()
        cmd = user_msg.lower().strip()

        # --- Command Matching ---

        # Helper to wrap HTML in artifact code block
        def artifact(html: str) -> str:
            return f"```html\n{self.css_styles()}\n{html}\n```"

        # Help
        if cmd in ["help", "/help", "?", "notes help"]:
            return artifact(self.render_help())

        # List all notes
        if cmd in ["notes", "/notes", "list notes", "show notes", "my notes"]:
            data = self.fetch_notes()
            if "error" in data:
                return artifact(self.render_error("Connection Error", f"Could not reach Adjutant Web: {data['error']}"))
            return artifact(self.render_note_list(data.get("notes", [])))

        # Read specific note
        match = re.match(r"^/?(?:read|show|open|view)\s+(note-\d+)$", cmd)
        if match:
            slug = match.group(1)
            note = self.fetch_note(slug)
            if not note or "error" in note:
                return artifact(self.render_error("Note not found", f"Could not find <code>{slug}</code>"))
            return artifact(self.render_note_card(note))

        # Search notes
        match = re.match(r'^/?search\s+["\']?(.+?)["\']?$', cmd)
        if match:
            query = match.group(1)
            data = self.fetch_notes({"search": query})
            if "error" in data:
                return artifact(self.render_error("Search Error", data["error"]))
            notes = data.get("notes", [])
            if not notes:
                return artifact(self.render_error("No results", f"No notes found matching \"{query}\""))
            return artifact(f'<div style="color:#888;margin-bottom:8px;">Search results for "{query}":</div>' + self.render_note_list(notes))

        # List categories
        if cmd in ["categories", "/categories", "list categories", "show categories"]:
            categories = self.fetch_categories()
            return artifact(self.render_categories(categories))

        # List tags
        if cmd in ["tags", "/tags", "list tags", "show tags", "all tags"]:
            tags = self.fetch_tags()
            return artifact(self.render_tags_list(tags))

        # Delete note
        match = re.match(r"^/?delete\s+(note-\d+)$", cmd)
        if match:
            slug = match.group(1)
            result = self.api_delete(f"/api/notes/{slug}")
            if result.get("success"):
                return artifact(self.render_deleted(slug))
            return artifact(self.render_error("Delete Failed", f"Could not delete {slug}: {result.get('error', 'Unknown error')}"))

        # --- Not a command, pass through to LLM ---
        # Return None or a specific signal to let OWUI know to use another model
        # For now, we return a helpful message
        return f"""I received: "{user_msg}"

This doesn't match a notes command. Available commands:
- `notes` — List all notes  
- `read note-X` — View a note
- `search "query"` — Find notes
- `help` — Show all commands

Or ask me naturally about your notes and I'll use the Adjutant Web tools to help!"""
