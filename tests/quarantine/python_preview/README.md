# Python Preview Test Quarantine

These files were moved out of default test discovery during M1 of the Python
TUI migration. They describe the deprecated `src/fortifylab` preview and should
not block the new skeleton unless a behavior is explicitly adopted by the new
architecture.

## Classification

| File | Classification | Notes |
| --- | --- | --- |
| `python_cli.py` | Rewrite | Replace with M1/M2 CLI and TUI entrypoint contracts. |
| `python_package_contract.py` | Rewrite | Old tests assert `src/` and preview version strings. |
| `python_operator_console.py` | Rewrite | Contains useful CLI/TUI status concepts, but old preview menu shape. |
| `python_tui_guided.py` | Rewrite later | Guided workflow belongs to M2+ and should use the new TUI model. |
| `python_tui_profiles.py` | Keep concept, rewrite | Profile expansion is valuable but should move to the new navigation/workflow model. |
| `python_orchestration_model.py` | Keep concept, rewrite | Dry-run/session concepts are useful for M3 operation adapters. |
| `python_operations.py` | Keep concept, rewrite | Operation catalog/redaction behavior belongs to M3. |
| `python_command_adapter.py` | Keep concept, rewrite | Secret redaction and command result structure remain important. |
| `python_config_engine.py` | Keep concept, rewrite | Config parser/backups/diffs/repair become M4 acceptance coverage. |
| `python_diagnostics_engine.py` | Keep concept, rewrite | Read-only collectors and bundles become M5 acceptance coverage. |
| `python_dashboard.py` | Quarantine | Dashboard preview is not part of M1; status panes may return in later TUI work. |

## M1 Rule

Default tests should cover only the new skeleton's supported surface:

- `./bin/fortifylab --help`
- `./bin/fortifylab tui --smoke-test`
- import sanity from the repo root package
- `start_wizard.sh` removed or reduced to an intentional shim

These quarantined tests can be copied back one behavior at a time when the
corresponding milestone accepts that behavior.
