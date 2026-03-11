# 2026-03-11 — Heartbeat Configuration Rename

**Status**: Complete (committed `bd48800`)

---

## What Changed

The autonomy subsystem was renamed to **heartbeat** to better reflect its role: the ongoing pulse of Adjutant's awareness and proactive monitoring. This is purely a configuration/naming change — no behavioral changes.

### Configuration Key Rename

| Old | New | Location |
|-----|-----|----------|
| `autonomy.enabled` | `heartbeat.enabled` | `adjutant.yaml` |
| `AutonomyConfig` | `HeartbeatConfig` | `src/adjutant/core/config.py` |
| `WIZARD_AUTONOMY_ENABLED` | `WIZARD_HEARTBEAT_ENABLED` | `src/adjutant/setup/steps/autonomy.py` |
| `WIZARD_AUTONOMY_MAX_PER_DAY` | `WIZARD_HEARTBEAT_MAX_PER_DAY` | `src/adjutant/setup/steps/autonomy.py` |

### File Names (Unchanged)

These were **not renamed** — only the config keys and internal variables changed:
- `src/adjutant/setup/steps/autonomy.py` — module still exists
- `docs/guides/autonomy.md` — guide still exists
- `docs/architecture/autonomy.md` — architecture doc still exists

---

## For Users

If you have an existing `adjutant.yaml`:

### Before
```yaml
autonomy:
  enabled: false
```

### After
```yaml
heartbeat:
  enabled: false
```

Run the setup wizard in repair mode to update automatically:
```bash
adjutant setup --repair
```

Or manually edit `adjutant.yaml` and change the `autonomy:` key to `heartbeat:`.

---

## For Developers

- All tests updated: `test_autonomy.py` now tests `WIZARD_HEARTBEAT_*` and `data["heartbeat"]`
- No behavior changes — the three-stage pipeline (pulse → escalation → review) is identical
- Model tier change for `/reflect` is separate (see `docs/reference/api-models.md`)

---

## Why Rename?

The term "autonomy" is overloaded in AI discussions. "Heartbeat" more clearly describes the ongoing, periodic monitoring behavior Adjutant provides — a steady pulse that keeps you informed without being intrusive.

The rename also consolidates all heartbeat-related configuration under one clear banner, making the config file easier to scan.

---

## Backward Compatibility

This is a **breaking change**. Existing `adjutant.yaml` files with `autonomy:` must be updated to `heartbeat:` or the config will not load. The code in `src/adjutant/core/config.py` will not recognize the old key.

No migration script is provided — manual edits or the setup wizard repair mode is required.
