# Setup Wizard — Implementation Reference

## Overview

`adjutant setup` is a bash-based interactive wizard that handles both fresh installs and repairs
of an existing adjutant installation. It is split across 8 scripts under `scripts/setup/`.

```
scripts/setup/
├── wizard.sh          # Entry point, flag parsing, orchestration, completion
├── helpers.sh         # Shared prompt/UI functions, yaml_set(), dry_run_would()
├── repair.sh          # Repair path (sourced by wizard.sh, not exec'd)
└── steps/
    ├── prerequisites.sh   # Step 0: read-only checks (no side effects)
    ├── install_path.sh    # Step 1: resolve/create install directory
    ├── identity.sh        # Step 2: soul.md, heart.md, registry.md
    ├── messaging.sh       # Step 3/4: Telegram token + chat ID, .env write
    ├── features.sh        # Step 5: news_config.json
    └── service.sh         # Step 6: chmod, rc-file alias, launchd/systemd/cron
```

### Execution paths

- **Fresh install** (`ADJ_DIR` unset or pointing to a non-existent directory): runs all 6 steps.
- **Repair** (existing install detected): sources `repair.sh`, which runs health checks and
  offers to fix each issue found. `repair.sh` inherits all exported variables from `wizard.sh`.

`repair.sh` is **sourced**, not exec'd — it runs in the same shell process as `wizard.sh` and
inherits `DRY_RUN` and all other exports automatically.

---

## Prompt helper functions (`helpers.sh`)

All interactive UI is funnelled through five functions. Understanding their output channels is
critical when debugging captured output or subshell corruption.

| Function | Captured via `$()` | Output channel | Notes |
|---|---|---|---|
| `wiz_confirm` | No — used for return code only | stdout (tty fallback) | Prints `[y/N]` prompt, returns 0/1 |
| `wiz_choose` | Yes | `/dev/tty` (stderr fallback) | Returns selected item on stdout |
| `wiz_input` | Yes | `/dev/tty` (stderr fallback) | Returns entered value on stdout |
| `wiz_multiline` | Yes | `/dev/tty` (stderr fallback) | Returns entered block on stdout |
| `wiz_secret` | Yes | `/dev/tty` (stderr fallback) | Returns entered secret on stdout |

**Why this matters**: functions called inside `$()` subshells must write their UI text to
`/dev/tty` (or stderr as fallback) — not stdout. Any text written to stdout inside a `$()`
substitution is captured into the variable, which corrupts the result (e.g. you get
`"  Installation path [...]\n/Users/state"` instead of `"/Users/state"`).

### `/dev/tty` failure pattern

Opening `/dev/tty` can fail in non-interactive contexts (CI, subshells with closed fds). The
safe pattern used throughout:

```bash
{ printf "..." >/dev/tty; } 2>/dev/null || printf "..." >&2
```

The outer `2>/dev/null` silences the bash-level "cannot open /dev/tty" error. Using
`>/dev/tty 2>/dev/null` inside the redirect does NOT suppress that error — bash emits it before
the redirect takes effect.

---

## `--dry-run` flag

### Activation

Parsed in `wizard.sh`:

```bash
if [[ "$1" == "--dry-run" ]]; then
    export DRY_RUN=true
fi
```

`DRY_RUN` is exported so it is visible to all sourced scripts and subshells.

### Behavior contract

| Category | Normal | Dry-run |
|---|---|---|
| Prompts | Interactive | Auto-accept defaults silently (UI text still shown) |
| Filesystem writes | Executed | Suppressed; `[DRY RUN] Would: ...` printed inline |
| `chmod` calls | Executed | Suppressed; printed inline |
| `curl` calls | Executed | Suppressed; printed inline |
| `opencode run` | Executed | Suppressed; printed inline |
| rc-file appends | Executed | Suppressed; printed inline |
| `launchctl`/`systemctl` | Executed | Suppressed; printed inline |
| `crontab` edits | Executed | Suppressed; printed inline |
| `yaml_set()` | Writes file | Suppressed; printed inline |
| Completion banner | Normal text | `[DRY RUN] Simulation complete. No changes were made.` |

### `dry_run_would()` helper

Defined in `helpers.sh`:

```bash
dry_run_would() {
    printf "[DRY RUN] Would: %s\n" "$*"
}
```

Used inline at every suppressed action site. Call it with a human-readable description of what
would have happened.

### Prompt auto-accept in dry-run

Each prompt function checks `DRY_RUN` before attempting to read input:

```bash
wiz_input() {
    local prompt="$1" default="$2"
    if [[ "$DRY_RUN" == "true" ]]; then
        { printf "  %s [%s]: %s\n" "$prompt" "$default" "$default" >/dev/tty; } 2>/dev/null \
            || printf "  %s [%s]: %s\n" "$prompt" "$default" "$default" >&2
        printf "%s" "$default"
        return 0
    fi
    # ... normal interactive path
}
```

The dry-run branch:
1. Writes the prompt + default to `/dev/tty` (or stderr fallback) so the UI is visible.
2. Writes only the default value to stdout — this is what `$()` captures.

`wiz_confirm` (not captured) uses stdout as fallback instead of stderr, which is fine.

### Guard pattern for side-effectful actions

Every action that would modify the filesystem, network, or system config is wrapped:

```bash
if [[ "$DRY_RUN" == "true" ]]; then
    dry_run_would "write $target_file"
else
    # real action here
fi
```

For multi-line writes (heredocs, `cat > file`), the entire block is inside the `else` branch.

### `yaml_set()` guard

`yaml_set()` in `helpers.sh` is shared infrastructure used by multiple scripts. It is guarded
once there, which automatically covers callers like `_features_yaml_set_bool` in `features.sh`
without needing additional guards in each caller.

---

## Known edge cases and gotchas

### Default install path resolves to `$(pwd)`

When `ADJ_DIR` is empty (fresh install simulation), the install path step resolves the default
to `$(pwd)`. In a non-interactive shell (e.g. a dry-run launched from `/Users`), this prints
`/Users` as the default path. This is cosmetically odd but functionally correct — no directory
is actually created in dry-run mode.

### Step 4 "No token provided" warning

In dry-run mode, `wiz_confirm "Do you have a Telegram bot token?"` auto-accepts its default
answer of `N`. This routes through the "create new bot" path in `messaging.sh` rather than the
"enter existing token" path. Because no token is entered, the `✗ No token provided` warning
appears at the end of Step 4. This is expected and cosmetically acceptable — the `.env` write
is suppressed regardless.

### `repair.sh` inherits `DRY_RUN` automatically

Because `repair.sh` is sourced (`. "$SETUP_DIR/repair.sh"`), it runs in the same shell process
and sees all exported variables including `DRY_RUN`. There is no need to re-parse `--dry-run`
inside `repair.sh`.

### Repair path vs. fresh install path

The wizard detects an existing installation by checking whether `ADJ_DIR` points to a directory
that contains `adjutant.yaml`. If yes, it sources `repair.sh`. If no, it runs the 6-step fresh
install. To force the fresh install path during dry-run testing:

```bash
ADJ_DIR="" adjutant setup --dry-run
```

To test the repair path on a live install:

```bash
adjutant setup --dry-run
```

---

## Files modified for dry-run

| File | What was changed |
|---|---|
| `scripts/setup/helpers.sh` | Added `dry_run_would()`; dry-run short-circuits in all 5 prompt functions; guard in `yaml_set()` |
| `scripts/setup/wizard.sh` | `--dry-run` flag parsing; dry-run banner after `wiz_banner`; guard in `_ensure_config()`; dry-run completion message; updated `--help` text |
| `scripts/setup/repair.sh` | Guards on all 7 fix actions: `adjutant.yaml` create, `chmod +x` CLI, rc-file alias append, `find chmod +x` scripts, `chmod 600 .env`, `mkdir -p` dirs, `crontab` add, listener `service.sh start` |
| `scripts/setup/steps/install_path.sh` | Guards on `mkdir -p` for install dir and the 8-dir structure loop |
| `scripts/setup/steps/identity.sh` | Guards on `cp` backups, `opencode run` + file write for soul/heart generation, all three template write functions |
| `scripts/setup/steps/messaging.sh` | Guards on both `curl` calls (`getMe`, `getUpdates`) and entire `_messaging_write_env()` |
| `scripts/setup/steps/features.sh` | Guard on `_features_write_news_config()` (`cat > news_config.json`) |
| `scripts/setup/steps/service.sh` | Guards on `_service_fix_permissions()`, `_service_setup_cli()`, `_service_install_launchd()`, `_service_install_systemd()`, `_service_install_news_cron()` |

`scripts/setup/steps/prerequisites.sh` was not modified — it performs read-only checks with no
side effects and needs no dry-run guards.
