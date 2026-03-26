# Roadmap

## Current: KB Explorer Rewrite

**Branch**: `feature/kb-explorer`  
**Status**: In Progress

Transform Adjutant Web from a single-notes-directory app into a read-only knowledge base explorer. See [kb-explorer-rewrite.md](kb-explorer-rewrite.md) for the full plan.

### Key changes

- Discover KBs by scanning a user-configured parent directory for `kb.yaml` files (Adjutant KB format)
- Flat categories replaced by recursive folder navigation
- Note metadata moves from YAML frontmatter to `.adjutant-web.json` sidecar files
- All KBs are read-only (no editing from Adjutant Web)
- MCP integration removed
- Home page becomes a KB browser with cards
- Sidebar becomes a recursive folder tree
- New `FolderNode` canvas node type for navigating into subfolders

## Phase 2: Local AI Integration

### Vision

Add semantic search and conversational AI capabilities, powered by local models via LM Studio. No data leaves the machine. Vector database runs in-process inside the API server.

### Architecture

```
┌──────────────────────────────────────────────────┐
│                 Adjutant Web Web                      │
│                                                  │
│  Search bar ──→ Semantic search results          │
│  Chat panel ──→ AI answers grounded in KB files  │
└──────────────────┬───────────────────────────────┘
                   │ REST API
┌──────────────────┼───────────────────────────────┐
│           Adjutant Web API (:3020)                   │
│                  │                               │
│  ┌───────────────┼────────────────────────────┐  │
│  │  New endpoints:                            │  │
│  │  POST /api/search/semantic                 │  │
│  │  POST /api/ai/ask                          │  │
│  │  GET  /api/embeddings/status               │  │
│  │  POST /api/embeddings/rebuild              │  │
│  └───────┬───────────────────┬────────────────┘  │
│          │                   │                   │
│  ┌───────┴──────┐    ┌──────┴───────┐            │
│  │   Vectra     │    │  LM Studio   │            │
│  │  (in-process │    │  (localhost   │            │
│  │   vectors)   │    │   :1234)     │            │
│  └──────────────┘    └──────────────┘            │
└──────────────────────────────────────────────────┘
```

### Why Vectra

Vectra runs fully in-process — no external database server. JSON files on disk, cosine similarity search, MongoDB-style metadata filtering. Scales to ~10k vectors comfortably.

### LM Studio

OpenAI-compatible local API for embeddings and chat completions. Recommended models:
- **Embeddings**: `nomic-embed-text`
- **Chat**: `llama-3.2-3b-instruct` or `phi-3-mini`

Graceful degradation — app works normally without LM Studio running.

### Implementation Phases

**2a: Embedding Infrastructure** — Vectra index, embedding service, sync pipeline, status/rebuild endpoints

**2b: Query Interface** — Semantic search endpoint, integrated into Home page search, visual indicators for match type

**2c: Conversational AI** — RAG pipeline, chat UI panel, context-aware scoping to current KB/folder

## Future Ideas

- **File watching**: Watch KB directories for external changes, auto-refresh canvas (see [future-features.md](future-features.md))
- **Note linking**: Bidirectional links between notes, wiki-style `[[note-title]]` syntax
- **Graph visualization**: Visual graph of note connections and semantic relationships
- **Smart tags**: AI-suggested tags based on note content
- **Summary generation**: Auto-generate note summaries for canvas preview cards
- **Mobile app**: React Native or PWA for mobile access
- **Write mode**: Optional per-KB write mode for creating/editing notes within Adjutant Web
- **Plugin system**: Extensible architecture for custom node types and tools
