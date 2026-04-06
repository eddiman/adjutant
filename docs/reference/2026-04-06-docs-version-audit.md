# Documentation & Version Audit — 2026-04-06

Comprehensive audit of all documentation files, version numbers, and cross-references in the Adjutant monorepo. Performed against commit `e877238` (main).

---

## VERSION MISMATCHES

### 1. Test asserts wrong version — `tests/unit/test_cli.py:44`
- Asserted `"0.1.0"` but `VERSION` file says `0.2.0`
- **Status:** FIXED — updated assertion to `"0.2.0"`

### 2. CHANGELOG doesn't document 0.2.0
- `CHANGELOG.md:10` said `[Unreleased] — Post-0.1.0 Hardening` but `VERSION` is already `0.2.0`
- **Status:** FIXED — changed header to `[0.2.0] — Unreleased — Post-0.1.0 Hardening`

### 3. `web/api/package.json` version is `1.0.0`
- `web/app/package.json` is `0.0.0` (placeholder), `site/package.json` is `0.0.0`
- The API was arbitrarily `1.0.0`
- **Status:** FIXED — changed to `0.0.0` for consistency with other workspaces

---

## DOCS vs CODE CONTRADICTIONS

### 4. Vision on Claude CLI — docs said "No", code says `True`
- `backend_claude_cli.py:119` sets `vision=True`
- Commit `2432d92` explicitly enabled this: "feat: enable vision on claude-cli backend via Read tool image injection"
- **Status:** FIXED — updated capability tables in `README.md`, `docs/intro.md`, `docs/guides/backends.md`. Removed stale "vision unsupported" error message example. Updated "when to use" sections and known behavioral differences.

### 5. Model listing on Claude CLI — docs said "No", code says `True`
- `backend_claude_cli.py:120` sets `model_listing=True`
- **Status:** FIXED — updated capability tables in `README.md`, `docs/intro.md`, `docs/guides/backends.md`

### 6. `adjutant doctor` output example was stale — `docs/guides/commands.md`
- Showed sample output listing only `opencode`
- Actual code checks backend-specific binary (`opencode` OR `claude`/`cloudcli`)
- **Status:** FIXED — updated sample output to show `claude`/`cloudcli` with comment explaining backend dependency. Added explanatory paragraph.

### 7. `https://localhost:3021` — `docs/guides/web.md:13`
- Initially flagged as wrong (assumed Vite serves HTTP), but HTTPS is correct for this project.
- **Status:** NOT A BUG — reverted change, `https://` is correct

### 8. `SECURITY_ASSESSMENT.md` references bash-era architecture
- The entire document (dated 2026-03-01) references the old bash implementation:
  - Line 5: "Adjutant v1.0 — single-user personal agent, bash/macOS/Linux"
  - References `scripts/messaging/adaptor.sh`, `scripts/common/env.sh`, `scripts/common/logging.sh`, `scripts/common/opencode.sh`
  - "Rate Limiting — **Not yet implemented**" — but rate limiting IS implemented in the Python rewrite
- **Status:** FIXED — added deprecation banner at top of file noting the document is outdated and a new assessment against the Python architecture is needed. Changed scope line to "pre-0.1.0".

### 9. `docs/guides/getting-started.md` — only mentioned OpenCode backend
- Lines 15-21: prerequisites only listed `opencode`, showed `opencode --version`
- `docs/getting-started/installation.md` (the Docusaurus version) correctly mentions both backends
- **Status:** FIXED — updated prerequisites to mention both backends with dual code examples, matching `installation.md`

---

## STRUCTURAL ISSUES

### 10. `guides/web.md` was not in the Docusaurus sidebar
- `site/sidebars.ts` listed 10 guides — `web` was missing
- **Status:** FIXED — added `'guides/web'` to sidebar between `news` and `troubleshooting`

### 11. Duplicate getting-started content
- `docs/guides/getting-started.md` — comprehensive guide (182 lines)
- `docs/getting-started/installation.md` + `telegram-setup.md` + `setup-wizard.md` + `first-message.md` — same content split into 4 pages
- The `guides/` version had the stale plist example; neither is excluded from Docusaurus
- **Status:** FIXED — added `guides/getting-started.md` to Docusaurus exclude list in `site/docusaurus.config.ts`. The file is kept for local readers (linked from `docs/README.md`) but no longer published to the docs site, avoiding a competing page. The canonical Docusaurus path is the 4-page split under `getting-started/`.

### 12. `CHANGELOG.md:146` referenced "adjutant-docs" as separate repo
- "Docusaurus documentation site (`adjutant-docs`)" — but after the monorepo consolidation, the docs site lives at `site/`
- **Status:** FIXED — changed to `site/`

### 13. `docs/guides/lifecycle.md:183` claimed `doctor` checks `jq` dependency
- Said: "Checks that all required tools are installed (`bash`, `curl`, `jq`, `python3`, `opencode`)"
- `jq` is not a real runtime dependency of the Python rewrite. Doctor does check it, but nothing uses it.
- **Status:** FIXED — updated text to say "bash, curl, python3, and your configured LLM backend binary". Note: `jq` is still checked by doctor in code (`cli.py:781`) — that's a separate code cleanup item.

---

## AMBIGUITIES / UNCLEARNESS

### 14. LaunchAgent plist name inconsistency
- `docs/guides/getting-started.md:128` uses label `com.adjutant.telegram`
- `docs/guides/lifecycle.md` used filename `adjutant.telegram.plist`
- The wizard (`src/adjutant/setup/steps/service.py:177`) generates `com.adjutant.telegram.plist`
- **Status:** FIXED — updated lifecycle.md to use `com.adjutant.telegram.plist` (matching wizard output)

### 15. `docs/guides/web.md` — port env var clarity
- Line 207: "API port configurable via `--port` flag or `ADJUTANT_WEB_PORT`"
- Verified: `web/api/src/config.ts:5` reads `process.env.ADJUTANT_WEB_PORT`, and `src/adjutant/cli.py:622` passes the `--port` value as `ADJUTANT_WEB_PORT` to the API subprocess.
- **Status:** NOT A BUG — documentation is correct

### 16. `docs/guides/backends.md` — streaming mentioned without context
- Table row: `| Streaming output | Yes | No |`
- **Status:** FIXED — added `(single-shot JSON)` clarification to table, and expanded the "Response style" behavioral difference paragraph to explain how streaming affects Telegram delivery.

---

## SUMMARY

| Priority | Total | Fixed | Not a bug |
|----------|-------|-------|-----------|
| P0 (wrong) | 5 | 5 | 0 |
| P1 (misleading) | 5 | 4 | 1 (#7) |
| P2 (cleanup) | 6 | 5 | 1 (#15) |
| **Total** | **16** | **14** | **2** |

All items resolved.
