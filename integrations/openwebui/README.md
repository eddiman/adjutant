# Adjutant Web Notes for Open WebUI

Interactive note management with HTML cards.

## Two Options

### 1. Pipe (Recommended) - `adjutant_web_pipe.py`

Direct HTML rendering, fast, no LLM delay for commands.

- Commands bypass LLM → instant HTML response
- After viewing a note, chat with LLM to modify it
- LLM uses MCP tools to update notes

### 2. Filter - `adjutant_web_filter.py`

Markdown-based, all responses go through LLM.

- Commands inject context into LLM prompt
- LLM formats and presents the data
- Slightly slower but more conversational

## Requirements

- Open WebUI v0.7.2+
- Adjutant Web server running (default: `http://host.docker.internal:3020`)

---

## Pipe Installation

1. Open **OWUI Admin → Functions**
2. Click **"+"** to create new function
3. Select type: **Pipe**
4. Name: `Adjutant Web Notes`
5. Copy contents of `adjutant_web_pipe.py` and paste
6. Click **Save**
7. The pipe appears as a selectable "model"

## Pipe Usage

Select "Adjutant Web Notes" as your model, then:

| Command | Result |
|---------|--------|
| `notes` | List all notes as HTML cards |
| `read note-1` | View note with full content |
| `search "meeting"` | Filter notes |
| `delete note-1` | Delete (immediate) |
| `categories` | List categories |
| `tags` | List all tags |
| `help` | Show all commands |

### Editing Flow

1. `read note-1` → See the note card
2. Switch to your LLM model
3. Say "change the title to X" or "add tag Y"
4. LLM uses MCP tools to update
5. `read note-1` again to see changes

---

## Filter Installation

1. Open **OWUI Admin → Functions**
2. Click **"+"** to create new function
3. Select type: **Filter**
4. Name: `Adjutant Web Notes Filter`
5. Copy contents of `adjutant_web_filter.py` and paste
6. Click **Save**
7. Assign filter to your model (Workspace → Models → Filters)

---

## Configuration (Valves)

| Setting | Default | Description |
|---------|---------|-------------|
| `adjutant_web_url` | `http://host.docker.internal:3020` | Adjutant Web API URL |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection Error" | Check Adjutant Web is running on port 3020 |
| HTML not rendering | Ensure OWUI version is 0.7.2+ |
| Docker can't reach host | Use `host.docker.internal` (default) |
