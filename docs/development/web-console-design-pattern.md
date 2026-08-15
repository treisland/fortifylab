# Web console design pattern

The Fortify Lab web console is an operator cockpit for disposable demo,
workshop, and classroom labs. It should feel like a polished enterprise console:
clear, calm, trustworthy, and direct about what is happening now.

## Visual direction

- Use an OpenText-adjacent palette: white surfaces, soft grays, black or
  near-black headings, strong blue primary actions, and restrained teal/green
  health accents.
- Keep warning and destructive states distinct: amber for caution, red for
  blocked or destructive outcomes.
- Prefer crisp borders, quiet shadows, and generous spacing over decorative
  gradients or terminal-heavy styling.
- Dark mode should be operational and restrained: charcoal backgrounds, readable
  contrast, muted blue actions, and the same status semantics as light mode.
- Typography should prioritize scanning. Use bold headings sparingly and keep
  dense operational labels compact.

## Layout model

Use an app shell with:

- a persistent left navigation rail for primary workspaces;
- a top context bar for profile, namespace, overall state, active job,
  connection/auth status, theme, and last update time;
- a dashboard landing page for the current lab picture and next best action;
- focused workspaces for deeper tasks such as logs, lifecycle, configuration,
  diagnostics, certificates, audit, and docs.

On small screens, collapse the rail into a drawer and keep the current page
title, state, and primary action visible.

## Dashboard pattern

The dashboard should answer three questions:

1. What is the lab state right now?
2. What needs attention?
3. Where should the operator go next?

Use summary cards for overall state, profile, namespace, active job, and recent
activity. Show the guided deployment timeline as a compact live view, not as the
only way to understand the system.

## Resource cards and uptime strips

Service cards should expose resource links without making the operator decode
Kubernetes objects. Each card should include:

- service name and URL;
- overall status;
- actions to open, view logs, diagnose, and get help;
- uptime-style indicators for DNS, TLS, HTTP, ingress, backend readiness, and
  last checked time.

When a check fails, prefer plain causes such as "Traefik default certificate,"
"Ingress has no address," or "DNS resolves elsewhere" over raw status only.

## Workspace patterns

- **Guided deploy:** show the current step, next safe action, recovery prompt,
  and compact history. Live cluster state must override stale saved progress.
- **Lifecycle controls:** separate whole-lab controls from individual service
  controls. Do not show raw script paths or sensitive values. Destructive
  actions need an impact summary and a deliberate confirmation button.
- **Logs:** use a dedicated logs workspace for recent logs, follow mode,
  pod/container context, search/filter, timestamps, pause/resume, copy/download,
  and previous-container support when available.
- **Audit:** show human-readable action entries with actor, action, target,
  duration, result, verification outcome, and affected resources.
- **Contextual help:** attach short help to pages, service cards, diagnostics,
  and guided steps. Link to durable docs instead of copying long runbooks into
  the UI.

## Back to top

Long pages such as Dashboard, Logs, Audit, Diagnostics, and Docs may use a
floating Back to top button. It should appear only after scrolling, be keyboard
accessible, avoid covering sticky actions, and respect reduced-motion settings.

## Accessibility and responsiveness

- Every clickable control needs visible hover and focus states.
- Status must not rely on color alone; pair color with labels or icons.
- Text must fit within cards, buttons, and status badges at laptop and mobile
  widths.
- Use stable dimensions for cards, uptime strips, toolbar buttons, and counters
  so live refreshes do not shift the layout.
- Keep one clear primary action per page or panel, with secondary actions nearby.

## Anti-patterns

- Do not build one long page where every workflow is hidden in expandable
  panels.
- Do not let persisted wizard history masquerade as live state.
- Do not expose shell script paths, decoded secrets, credentials, private keys,
  license contents, or raw tokens in normal UI.
- Do not use decorative gradient blobs, oversized marketing heroes, or
  stock-like imagery in the operator console.
- Do not make destructive actions depend on awkward typed phrases when a clear
  impact review and deliberate confirmation control will do.
- Do not refresh by flashing the screen; update regions in place and preserve
  operator context.
