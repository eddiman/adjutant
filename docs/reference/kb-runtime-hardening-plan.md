# KB Runtime Hardening Plan

Last updated: 2026-03-06

## Purpose

This plan defines the next Adjutant-side changes required to support operational knowledge bases in a generic way.

It is intentionally KB-agnostic.

Adjutant must not contain direct portfolio-specific logic, portfolio-specific runtime assumptions, or portfolio-specific tests. It should manage any knowledge base through the same registry, query, scheduling, and safety contracts.

## Goals

- make KB discovery registry-driven
- make KB operations executable by KB name, not by hardcoded external paths
- support structured-state KBs without coupling Adjutant to one KB implementation
- keep safety-sensitive KB behavior generic and explicit
- ensure Adjutant tests only generic KB framework behavior

## Non-goals

- implementing trading logic in Adjutant
- adding KB-specific runtime branches for `portfolio`
- writing tests that assert domain-specific files or workflows inside a specific KB

## Current gaps

- KB query flow is registry-driven, but scheduled KB operations are still defined as direct external script paths in `adjutant.yaml`
- `portfolio` is not registered in `~/.adjutant/knowledge_bases/registry.yaml`, even though Adjutant schedules point at its scripts
- Adjutant has no generic concept of running a named KB operation such as `fetch` or `reconcile`
- KB guidance assumes `data/current.md` is primary, but does not clearly describe structured-state-first KBs
- reflect guidance is too permissive for safety-sensitive operational KBs

## Design principles

### 1. KBs are addressed by name

Adjutant should resolve KB path, access level, and metadata from `knowledge_bases/registry.yaml`.

No framework behavior should depend on a specific KB path being hardcoded in `adjutant.yaml`.

### 2. Operations are generic

Adjutant should support generic KB operations such as:

- `fetch`
- `news`
- `analyze`
- `reconcile`

These are capability-level concepts. Whether a given KB implements one or more of them is a KB concern.

### 3. Adjutant owns orchestration, not domain logic

Adjutant decides:

- when KB operations run
- how KBs are discovered
- how KBs are queried
- what safety rules apply at the framework level

The KB decides:

- what its scripts do
- what its structured state means
- what reconciliation means inside that domain

### 4. Tests stay generic

Adjutant test coverage must validate framework behavior only.

Examples of valid Adjutant tests:

- registry lookup works
- `kb query` resolves by name
- `kb run` dispatches to a KB-defined operation
- schedules call wrapper scripts correctly
- read-write KBs respect reflect safety constraints

Examples of invalid Adjutant tests:

- asserting `signals.json` contents for `portfolio`
- asserting Nordnet-specific behavior
- asserting financial reconciliation semantics

## Proposed architecture changes

## Phase 1 - Formalize generic KB runtime contract

### Objective

Define how Adjutant discovers and runs KB operations generically.

### Changes

- document required registry fields in `docs/guides/knowledge-bases.md`
- define a generic KB operation contract:
  - operation name
  - expected script location inside the KB
  - stdout contract
  - allowed side effects
- document how structured-state KBs should expose rendered status via `data/current.md`

### Deliverables

- updated `docs/guides/knowledge-bases.md`
- updated KB template guidance

### Acceptance criteria

- a KB can be described and operated without naming a specific implementation
- docs distinguish rendered views from canonical state cleanly

## Phase 2 - Add generic KB runner

### Objective

Allow Adjutant to invoke KB operations by KB name.

### Proposed interface

```bash
bash scripts/capabilities/kb/run.sh <kb-name> <operation>
```

Examples:

```bash
bash scripts/capabilities/kb/run.sh my-kb fetch
bash scripts/capabilities/kb/run.sh my-kb analyze
bash scripts/capabilities/kb/run.sh my-kb reconcile
```

### Required behavior

- resolve KB path from registry
- validate KB exists and path is readable
- resolve operation to a KB-local script conventionally
- return `OK:<message>` or `ERROR:<reason>`
- fail clearly if the KB does not implement the requested operation

### Files likely affected

- new `scripts/capabilities/kb/run.sh`
- `scripts/capabilities/kb/manage.sh`
- possibly `adjutant` CLI dispatch if a user-facing command is added later

### Acceptance criteria

- no direct path knowledge is required to run KB operations
- wrapper behavior is identical for all KBs

## Phase 3 - Decouple schedules from external KB paths

### Objective

Move Adjutant schedules away from hardcoded external KB script paths.

### Changes

- update `adjutant.yaml` schedules to call Adjutant-owned wrappers
- define schedules in terms of KB name plus operation
- preserve log path behavior, but prefer wrapper-owned logging where possible

### Example direction

Instead of:

```yaml
script: "/absolute/path/to/kb/scripts/fetch.sh"
```

Use a framework-owned wrapper script that runs:

```bash
bash scripts/capabilities/kb/run.sh <kb-name> fetch
```

### Acceptance criteria

- schedules are portable at the Adjutant layer
- Adjutant remains the entrypoint for orchestration
- no schedule requires KB-specific framework logic

## Phase 4 - Add generic safety policy for operational KBs

### Objective

Prevent read-write and safety-sensitive KBs from performing unsafe actions during broad Adjutant flows like reflect.

### Changes

- update `prompts/review.md`
- clarify that read-write KBs may:
  - refresh stale data
  - rebuild rendered views
  - run reconciliation or consistency repairs
- clarify that they may not:
  - execute sensitive real-world actions unless explicitly instructed by the user

### Notes

This policy must stay generic. It should refer to safety-sensitive or operational KBs broadly, not to trading specifically.

### Acceptance criteria

- reflect remains useful for operational KBs
- reflect cannot be interpreted as blanket authorization for sensitive actions

## Phase 5 - Update KB scaffolding for structured-state KBs

### Objective

Make advanced KB patterns first-class in Adjutant templates and docs.

### Changes

- update `templates/kb/agents/kb.md`
- update `docs/guides/knowledge-bases.md`
- add guidance for:
  - `data/current.md` as landing page
  - canonical JSON state for automation-heavy KBs
  - markdown as rendered reporting where applicable

### Optional enhancements

- add optional advanced scaffold directories:
  - `data/analysis/`
  - `data/positions/`
  - `state/`
  - `docs/reference/`

### Acceptance criteria

- future structured-state KBs can follow a supported pattern without custom framework changes

## Phase 6 - Register KBs consistently

### Objective

Ensure registry remains the single source of truth for KB discovery and execution.

### Changes

- require operational KBs to be present in `knowledge_bases/registry.yaml`
- align docs and operator guidance so scheduling a KB without registering it is treated as misconfiguration

### Acceptance criteria

- query and run paths both depend on registration
- no split-brain between schedule config and KB registry

## Phase 7 - Add generic Adjutant tests

### Objective

Protect the framework layer without coupling tests to a specific KB implementation.

### Test scope

- registry lookup and metadata retrieval
- `kb_query` by name
- `kb run` resolution and error handling
- schedule wrapper invocation
- generic reflect safety boundaries for read-write KBs

### Explicit constraint

Adjutant tests must not assert:

- portfolio-specific files
- finance-specific semantics
- domain-specific outputs from a single KB

### Acceptance criteria

- the generic KB runtime is test-backed
- KB-specific behavior remains tested outside Adjutant

## Implementation order

1. formalize generic KB runtime contract in docs
2. add `kb run` wrapper
3. move schedules to wrapper-based execution
4. tighten reflect safety policy
5. update KB templates and docs for structured-state KBs
6. add generic framework tests

## Definition of done

Adjutant is done with this plan when:

- KB query and KB run are both registry-driven
- schedules no longer depend on KB-specific external script paths
- safety-sensitive KB behavior is documented generically
- Adjutant tests remain KB-agnostic
- no Adjutant code path contains portfolio-specific assumptions

## Implementation status

Completed in this repo:

- generic `kb run` capability added
- CLI support for `adjutant kb run <name> <operation>` added
- KB operation resolution moved into generic registry-backed helpers
- schedule runtime extended to support `kb_name` + `kb_operation`
- live schedule config migrated away from direct KB script paths
- KB docs and templates updated for structured-state KBs
- reflect guidance updated for safety-sensitive operational KBs
- generic tests added for KB run and KB-backed schedule execution
- KB scaffold extended with `state/` and `docs/reference/`

Current outcome:

- Adjutant now supports registry-driven KB query and registry-driven KB operation execution
- schedules can target KB operations without embedding KB-specific framework logic
- tests remain KB-agnostic
