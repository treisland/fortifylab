# Phase 4 preview release notes

Phase 4 turns the Python foundation into an operator-facing runtime while the
Bash wizard remains available as the production fallback.

Initial testing path:

```bash
./bin/fortifylab doctor --environment
./bin/fortifylab doctor --compatibility
./bin/fortifylab web --check
./bin/fortifylab web --check --bind 0.0.0.0 --allow-lan --token test-token
```

Runtime notes:

- Python commands write redacted runtime logs under `.fortifylab/logs/` by
  default.
- `FORTIFYLAB_LOG_DIR` can move logs to another directory for demos or support
  bundles.
- Compatibility checks are read-only and summarize `.env`, cert, secret, and
  entrypoint readiness.
- Mutating Python operations continue to require explicit execution flags.

Known boundary:

- `./start_wizard.sh` remains the primary guided deployment entrypoint until
  Python-backed flows have completed manual testing.
