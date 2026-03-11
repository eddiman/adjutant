# Adjutant Documentation

Adjutant is a persistent autonomous agent framework that runs on your local machine. It listens for messages from a messaging backend, routes them through a backend-agnostic dispatcher, and responds via OpenCode-powered AI or built-in commands.

---

## Guides

For people using Adjutant.

| Document | What it covers |
|----------|---------------|
| [Getting Started](guides/getting-started.md) | Install, setup wizard, send your first message |
| [Configuration](guides/configuration.md) | `adjutant.yaml`, `.env`, identity files (`soul.md`, `heart.md`, `registry.md`) |
| [Commands](guides/commands.md) | All Telegram slash commands and `adjutant` CLI subcommands |
| [Knowledge Bases](guides/knowledge-bases.md) | Creating, structuring, and querying knowledge bases |
| [Schedules](guides/schedules.md) | Cron-based scheduled jobs, KB operations, registry management |
| [Autonomy](guides/autonomy.md) | Autonomous pulse/review cycles, notification budget, dry-run mode |
| [Lifecycle](guides/lifecycle.md) | Start, stop, pause, kill, recover, and update |

---

## Architecture

For people who want to understand how Adjutant works internally.

| Document | What it covers |
|----------|---------------|
| [Overview](architecture/overview.md) | High-level diagram and layer summary |
| [Messaging](architecture/messaging.md) | Adaptor contract, dispatcher, Telegram adaptor internals |
| [Identity & Agent](architecture/identity.md) | Three-layer identity model and OpenCode integration |
| [State & Lifecycle](architecture/state.md) | Lockfiles, state files, lifecycle state machine, rate limiting |
| [Autonomy](architecture/autonomy.md) | Autonomous cycle architecture, pulse/review/escalation design |
| [Design Decisions](architecture/design-decisions.md) | Why things are the way they are |

---

## Development

For people extending or contributing to Adjutant.

| Document | What it covers |
|----------|---------------|
| [Adaptor Guide](development/adaptor-guide.md) | How to build a new messaging backend (Slack, Discord, CLI, etc.) |
| [Plugin Guide](development/plugin-guide.md) | How to add a new capability script |
| [Setup Wizard Internals](development/setup-wizard.md) | `adjutant setup` implementation: steps, dry-run, prompt helpers |
| [Testing](development/testing.md) | Running the test suite, tier overview, isolation model |

---

## Reference

Background context and historical records.

| Document | What it covers |
|----------|---------------|
| [Landscape](reference/landscape.md) | How Adjutant compares to OpenClaw and NanoClaw |
| [Testing Appendix](reference/testing-appendix.md) | Historical bats test listings (pre-Python rewrite; superseded by pytest) |
| [Deployment Readiness Assessment](reference/deployment-readiness.md) | Pre-release checklist and findings (2026-03-01) |
| [Framework Plan](reference/framework-plan.md) | Original 6-phase development plan |
