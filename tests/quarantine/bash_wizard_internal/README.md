# Bash Wizard Internal Test Quarantine

These tests covered the retired Bash wizard implementation. M1 replaces
`start_wizard.sh` with a compatibility shim to the Python CLI/TUI skeleton, so
these tests are preserved for reference but excluded from default unittest
discovery.

Behavior that remains supported should be rewritten as Python CLI/TUI, operation
adapter, config, diagnostics, navigation parity, or runbook tests in later
milestones.
