# Web console manual test notes

The Fortify Lab web console is a companion operator view. Phase 6 lifecycle
surfaces are intentionally preview-only until backend execution endpoints,
durable job state, and audit persistence are wired and reviewed.

## Secure lifecycle management

Before enabling or validating lifecycle controls, confirm these boundaries:

1. Start the console on `127.0.0.1` for local review, or use LAN mode only with a
   non-secret access token supplied outside committed files.
2. Open the console and verify **Security posture** reports the bind host, access
   mode, token requirement, read-only action mode, and redaction boundary.
3. Verify **Lifecycle controls** displays action previews from backend metadata
   when available. If `/api/lifecycle/actions` is unavailable, the UI should
   fall back to operation identifiers from `/api/status` and keep execution
   disabled.
4. Select representative start, stop, secret, runbook, log, and destroy previews.
   Confirm mutating actions are marked as mutating, destructive actions show the
   exact typed confirmation phrase, and the command preview never exposes
   passwords, tokens, private keys, licenses, or environment values.
5. Confirm **Confirmation preview** is read-only and the execution button remains
   disabled while the console reports `preview-only`.
6. Confirm the job placeholder says no lifecycle job has been submitted from the
   web console.
7. Confirm **Action audit** shows existing entries when an audit endpoint returns
   them, or a graceful placeholder when no entries or endpoint are available.

## Manual browser checks

Use both light and dark theme settings. At desktop width, the lifecycle panel
should sit in the active workspace below the service launchpad, while security
posture and audit panels should sit with evidence and health. At mobile width,
summary cards, lifecycle previews, confirmation preview, job status, and audit
entries should stack without clipped text.

Refresh behavior should remain read-only. A partial API failure may mark the
connection as partial data, but it should not hide the static security and
lifecycle placeholders. No manual test should click through to execute a
lifecycle action until the backend execution and audit contract has a separate
review.
