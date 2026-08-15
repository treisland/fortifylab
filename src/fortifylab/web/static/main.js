const token = new URLSearchParams(window.location.search).get("token");
const refreshIntervalMs = 5000;
const themeStorageKey = "fortifylab.theme";
let refreshInFlight = false;
let focusedPanel = null;
let focusedPlaceholder = null;
let selectedLifecycleActionId = null;
let lifecycleSubmitting = false;
let panelFocusClosing = false;
const panelFocusAnimationMs = 180;
const state = document.querySelector("#connection-state");
const lastUpdated = document.querySelector("#last-updated");
const store = {
  status: null,
  deploymentStatus: null,
  guide: null,
  config: null,
  diagnostics: null,
  logs: null,
  certificates: null,
  routes: null,
  services: null,
  serviceHealth: null,
  securityPosture: null,
  lifecycleActions: null,
  lifecycleAudit: null,
  operationJobs: null,
};

function panelTitle(panel) {
  return panel.querySelector(".panel-heading span")?.textContent?.trim() || panel.dataset.panel || "Panel";
}

function closeFocusedPanel() {
  const overlay = document.querySelector("#panel-focus-overlay");
  if (!focusedPanel || !focusedPlaceholder) {
    if (overlay) overlay.remove();
    document.body.classList.remove("panel-focus-open");
    return;
  }
  if (panelFocusClosing) return;
  panelFocusClosing = true;
  overlay?.classList.add("is-closing");
  focusedPanel.classList.add("is-collapsing");
  window.setTimeout(() => {
    if (focusedPanel && focusedPlaceholder) {
      focusedPanel.classList.remove("is-focused-panel", "is-collapsing");
      focusedPlaceholder.replaceWith(focusedPanel);
    }
    focusedPanel = null;
    focusedPlaceholder = null;
    panelFocusClosing = false;
    document.body.classList.remove("panel-focus-open");
    if (overlay) overlay.remove();
  }, panelFocusAnimationMs);
}

function openFocusedPanel(panel) {
  if (focusedPanel === panel) {
    closeFocusedPanel();
    return;
  }
  closeFocusedPanel();
  focusedPanel = panel;
  focusedPlaceholder = document.createElement("div");
  focusedPlaceholder.className = "panel-focus-placeholder";
  panel.before(focusedPlaceholder);

  const overlay = document.createElement("div");
  overlay.id = "panel-focus-overlay";
  overlay.className = "panel-focus-overlay";
  const title = panelTitle(panel);
  overlay.innerHTML = `<div class="panel-focus-shell" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)} fullscreen panel"><div class="panel-focus-bar"><div><span>Focused panel</span><strong>${escapeHtml(title)}</strong></div><button type="button" class="panel-focus-close" aria-label="Collapse fullscreen panel">Collapse</button></div><div class="panel-focus-stage"></div></div>`;
  document.body.appendChild(overlay);
  panel.classList.add("is-focused-panel");
  overlay.querySelector(".panel-focus-stage").appendChild(panel);
  overlay.querySelector(".panel-focus-close").addEventListener("click", closeFocusedPanel);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeFocusedPanel();
  });
  overlay.querySelector(".panel-focus-close").focus();
  document.body.classList.add("panel-focus-open");
}

function setupPanelFocus() {
  for (const panel of document.querySelectorAll("[data-panel]")) {
    const heading = panel.querySelector(".panel-heading");
    if (!heading || heading.querySelector(".panel-focus-button")) continue;
    const meta = heading.querySelector("strong");
    const actions = document.createElement("div");
    actions.className = "panel-heading-actions";
    if (meta) actions.appendChild(meta);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "panel-focus-button";
    button.title = `Open ${panelTitle(panel)} fullscreen`;
    button.setAttribute("aria-label", `Open ${panelTitle(panel)} fullscreen`);
    button.addEventListener("click", () => openFocusedPanel(panel));
    actions.appendChild(button);
    heading.appendChild(actions);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeFocusedPanel();
  });
}

function headers() {
  return token ? { "X-FortifyLab-Token": token } : {};
}

function applyTheme(choice) {
  const normalized = ["system", "light", "dark"].includes(choice) ? choice : "system";
  if (normalized === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.dataset.theme = normalized;
  }
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.themeChoice === normalized));
  }
}

function setupThemeSwitch() {
  let saved = "system";
  try {
    saved = window.localStorage.getItem(themeStorageKey) || "system";
  } catch (error) {
    saved = "system";
  }
  applyTheme(saved);
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.addEventListener("click", () => {
      const choice = button.dataset.themeChoice || "system";
      try {
        window.localStorage.setItem(themeStorageKey, choice);
      } catch (error) {
        // Theme preference is optional; continue if browser storage is unavailable.
      }
      applyTheme(choice);
    });
  }
}

async function loadJson(path) {
  const response = await fetch(path, { headers: headers() });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    const message = payload.error?.message || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload.data || {};
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    const message = payload.error?.message || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload.data || {};
}

function target(name) {
  return document.querySelector(`[data-content="${name}"]`);
}

function setText(name, value) {
  const node = target(name);
  if (node) node.textContent = value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function pretty(value) {
  return String(value || "unknown").replace(/_/g, " ");
}

function pill(value) {
  const stateName = String(value || "unknown");
  return `<span class="pill" data-state="${escapeHtml(stateName)}">${escapeHtml(pretty(stateName))}</span>`;
}

function empty(message) {
  return `<p class="empty">${escapeHtml(message)}</p>`;
}

function fail(panel, error) {
  const node = target(panel);
  if (node) node.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
}

function commandLine(parts) {
  return Array.isArray(parts) ? parts.join(" ") : String(parts || "");
}

function allSteps() {
  const guided = store.guide?.steps || [];
  const live = store.deploymentStatus?.steps || [];
  return guided.length ? guided : live;
}

function focusStep() {
  const steps = allSteps();
  return steps.find((step) => ["blocked", "failed", "in_progress"].includes(step.state)) || steps.find((step) => step.state !== "complete") || steps[0] || null;
}

function collectPods() {
  const pods = [];
  for (const step of store.deploymentStatus?.steps || []) {
    for (const pod of step.pods || []) {
      pods.push({ ...pod, step_label: step.label, step_id: step.step_id });
    }
  }
  return pods;
}

function collectRoutes() {
  const routes = [];
  for (const step of store.deploymentStatus?.steps || []) {
    for (const route of step.routes || []) {
      routes.push({ ...route, step_label: step.label, step_id: step.step_id });
    }
  }
  return routes;
}

function renderRefreshCadence() {
  if (!lastUpdated) return;
  const generated = store.deploymentStatus?.generated_at ? new Date(store.deploymentStatus.generated_at) : new Date();
  const when = Number.isNaN(generated.valueOf()) ? "just now" : generated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  lastUpdated.textContent = `Updated ${when} · refreshes every ${Math.round(refreshIntervalMs / 1000)}s`;
}

function renderSummary() {
  const statusData = store.status || {};
  const deployment = store.deploymentStatus || {};
  const guide = store.guide || {};
  const stateValue = deployment.overall_state || guide.overall_state || statusData.mode || "unknown";
  setText("summary-state", pretty(stateValue));
  setText("summary-profile", deployment.profile || guide.profile || "pending");
  setText("summary-namespace", deployment.namespace || "not reported");
  setText("summary-operations", String((statusData.operations || []).length));
  const posture = store.securityPosture?.actions;
  setText("summary-security", posture ? pretty(posture.mode) : "preview");
  renderRefreshCadence();
}

function renderDeployment(data) {
  const steps = data.steps || [];
  const complete = steps.filter((step) => step.state === "complete").length;
  setText("timeline-progress", `${complete} / ${steps.length}`);
  target("deployment").innerHTML = steps.length
    ? `<ol class="timeline">${steps.map((step) => `
        <li class="timeline-step">
          <span class="step-index">${escapeHtml(step.index || "-")}</span>
          <div class="step-body">
            <div class="step-title"><strong>${escapeHtml(step.label || step.step_id || "Deployment step")}</strong>${pill(step.state)}</div>
            <div class="step-detail">${escapeHtml(step.detail || "Waiting for live detail.")}</div>
            <div class="step-meta">${escapeHtml((step.pods || []).length)} pods · ${escapeHtml(step.hint_count || 0)} hints</div>
          </div>
        </li>`).join("")}</ol>`
    : empty("No guided deployment steps reported.");
}

function renderWorkspace() {
  const step = focusStep();
  const pods = collectPods();
  const routes = collectRoutes();
  const hints = store.diagnostics?.findings || [];
  setText("workspace-state", step ? pretty(step.state) : "Standby");
  if (!step) {
    target("workspace").innerHTML = empty("No active deployment step is available yet. The console will populate as status data arrives.");
    return;
  }
  const relatedPods = pods.filter((pod) => pod.step_id === step.step_id || pod.step_label === step.label);
  const relatedRoutes = routes.filter((route) => route.step_id === step.step_id || route.step_label === step.label);
  const relatedHints = hints.filter((hint) => hint.step_id === step.step_id || hint.step_label === step.label);
  target("workspace").innerHTML = `
    <div class="focus-card">
      <div class="focus-header">
        <div>
          <h2>${escapeHtml(step.label || step.step_id || "Deployment step")}</h2>
          <p>${escapeHtml(step.detail || "Waiting for live detail.")}</p>
        </div>
        ${pill(step.state)}
      </div>
      <div class="metric-grid">
        <div class="metric"><span>Pods</span><strong>${relatedPods.length}</strong></div>
        <div class="metric"><span>Routes</span><strong>${relatedRoutes.length}</strong></div>
        <div class="metric"><span>Hints</span><strong>${relatedHints.length}</strong></div>
        <div class="metric"><span>Elapsed</span><strong>${escapeHtml(step.elapsed_seconds || 0)}s</strong></div>
      </div>
      ${renderPodList(relatedPods)}
      ${renderHintList(relatedHints)}
    </div>`;
}

function renderPodList(pods) {
  if (!pods.length) return empty("No pods are associated with the active step yet.");
  return `<ul class="card-list">${pods.map((pod) => `
    <li class="card-row">
      <div class="row-main"><strong>${escapeHtml(pod.name)}</strong>${pill(pod.reason || pod.phase)}</div>
      <div class="row-note">Ready ${escapeHtml(pod.ready ?? 0)} / ${escapeHtml(pod.total ?? 0)} · Restarts ${escapeHtml(pod.restarts ?? 0)}</div>
    </li>`).join("")}</ul>`;
}

function renderHintList(hints) {
  if (!hints.length) return "";
  return `<ul class="card-list">${hints.map((hint) => `
    <li class="card-row">
      <div class="row-main"><strong>${escapeHtml(hint.message || hint.reason || "Diagnostic hint")}</strong>${pill(hint.severity)}</div>
      <div class="row-note">${escapeHtml(hint.next_inspection || "No next inspection reported.")}</div>
    </li>`).join("")}</ul>`;
}

function renderLogs(data) {
  const resources = data.resources || [];
  const pods = resources.flatMap((resource) => (resource.pods || []).map((pod) => ({ ...pod, step_label: resource.step_label })));
  setText("logs-count", `${pods.length} pods`);
  target("logs").innerHTML = pods.length
    ? `<ul class="card-list">${pods.slice(0, 8).map((pod) => `
        <li class="card-row">
          <div class="row-main"><strong>${escapeHtml(pod.step_label || "Pod logs")}</strong><span>${escapeHtml(pod.name)}</span></div>
          <div class="log-actions">
            <button type="button" class="secondary-action" data-log-action="logs.${escapeHtml(pod.name)}">View recent logs</button>
          </div>
          <code class="command">${escapeHtml(commandLine(pod.recent_command))}</code>
          ${renderLogOutput(`logs.${pod.name}`)}
        </li>`).join("")}</ul>`
    : empty("No pod log options reported yet.");
  bindLogControls();
}

function renderLogOutput(operationId) {
  const job = latestJobForAction(operationId);
  if (!job) return "";
  const detail = job.execution?.detail || job.message || "Log request submitted.";
  return `<pre class="log-output">${escapeHtml(detail)}</pre>`;
}

function bindLogControls() {
  for (const button of document.querySelectorAll("[data-log-action]")) {
    button.addEventListener("click", () => submitReadOnlyOperation(button.dataset.logAction));
  }
}

async function submitReadOnlyOperation(operationId) {
  if (!operationId) return;
  try {
    const jobPayload = await postJson("/api/operations/jobs", { operation_id: operationId });
    const finishedJob = await waitForJob(jobPayload.job?.job_id);
    const job = finishedJob || jobPayload.job;
    const existingJobs = store.operationJobs?.jobs || [];
    store.operationJobs = { jobs: [job, ...existingJobs.filter((item) => item.job_id !== job.job_id)] };
  } catch (error) {
    store.operationJobs = { jobs: [{ operation_id: operationId, status: "failed", message: error.message }] };
  } finally {
    if (store.logs) renderLogs(store.logs);
    if (store.lifecycleActions) renderLifecycleActions(store.lifecycleActions);
  }
}

function renderDiagnostics(data) {
  const findings = data.findings || [];
  const warnings = data.tool_warnings || [];
  const total = findings.length + warnings.length;
  setText("health-count", String(total));
  target("health").innerHTML = total
    ? `<ul class="card-list">
        ${warnings.map((warning) => `<li class="card-row"><div class="row-main"><strong>Tool warning</strong>${pill("warning")}</div><div class="row-note">${escapeHtml(warning)}</div></li>`).join("")}
        ${findings.slice(0, 6).map((finding) => `<li class="card-row"><div class="row-main"><strong>${escapeHtml(finding.step_label || finding.reason || "Finding")}</strong>${pill(finding.severity)}</div><div class="row-note">${escapeHtml(finding.message || "No message reported.")}</div></li>`).join("")}
      </ul>`
    : empty("No deployment diagnostics reported.");
}

function renderConfiguration(data) {
  const sections = data.sections || [];
  setText("configuration-count", `${sections.length} sections`);
  target("configuration").innerHTML = `
    <dl class="dl-grid">
      <div><dt>Sections</dt><dd>${sections.length ? escapeHtml(sections.join(", ")) : "Not reported"}</dd></div>
      <div><dt>Secrets redacted</dt><dd>${data.secrets_redacted ? "yes" : "unknown"}</dd></div>
    </dl>`;
}

function renderRoutes() {
  const health = store.serviceHealth?.services || [];
  if (health.length) {
    setText("launchpad-count", `${health.length} services`);
    target("routes").innerHTML = `<ul class="service-grid">${health.map((service) => {
      const state = serviceState(service);
      const history = uptimeHistory(state, service.service_id);
      return `<li class="service-card">
        <div class="row-main"><strong>${escapeHtml(service.label || service.service_id || "Service")}</strong>${pill(state)}</div>
        ${service.url ? `<a href="${escapeHtml(service.url)}" target="_blank" rel="noreferrer">${escapeHtml(service.url)}</a>` : `<span class="row-note">No URL reported.</span>`}
        <div class="uptime-strip" aria-label="${escapeHtml(service.label || service.service_id || "Service")} health history">${history.map((entry) => `<span data-state="${escapeHtml(entry)}"></span>`).join("")}</div>
        <div class="service-meta">
          ${checkPill(service, "dns")}
          ${checkPill(service, "http")}
          ${checkPill(service, "tls")}
          ${checkPill(service, "ingress")}
        </div>
        ${renderServiceHint(service)}
      </li>`;
    }).join("")}</ul>`;
    return;
  }
  const routes = collectRoutes();
  setText("launchpad-count", `${routes.length} services`);
  if (!routes.length) {
    target("routes").innerHTML = empty("No route or uptime data is available yet. Service cards will appear when the live deployment status reports ingress hosts.");
    return;
  }
  target("routes").innerHTML = `<ul class="service-grid">${routes.map((route) => {
    const ready = route.ingress_present && route.endpoints_ready ? "ready" : route.ingress_present ? "warning" : "missing";
    const url = route.host ? `https://${route.host}` : "";
    return `<li class="service-card">
      <div class="row-main"><strong>${escapeHtml(route.step_label || route.service_name || route.host || "Service")}</strong>${pill(ready)}</div>
      ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>` : `<span class="row-note">No host reported.</span>`}
      <div class="service-meta">
        ${pill(route.tls_secret ? "tls" : "tls missing")}
        ${pill(route.endpoints_ready ? "endpoints ready" : "endpoints pending")}
      </div>
    </li>`;
  }).join("")}</ul>`;
}

function serviceState(service) {
  const checks = Object.values(service.checks || {});
  if (!checks.length) return "unknown";
  if (checks.some((check) => check.state === "blocked")) return "down";
  if (checks.some((check) => check.state === "warning")) return "degraded";
  if (checks.every((check) => check.state === "ok")) return "up";
  return "unknown";
}

function checkPill(service, key) {
  const check = service.checks?.[key];
  if (!check) return pill(`${key} unknown`);
  return pill(`${key} ${check.state || "unknown"}`);
}

function uptimeHistory(state, seed) {
  const base = Array.from({ length: 17 }, () => state);
  if (state === "unknown") return base;
  const offset = String(seed || "").length % base.length;
  base[offset] = state === "up" ? "unknown" : "up";
  return base;
}

function renderServiceHint(service) {
  const hint = (service.hints || [])[0];
  if (!hint) return "";
  return `<div class="row-note">${escapeHtml(hint.message || "Health check needs attention.")}</div>`;
}

function renderCertificates(data) {
  setText("cert-state", data.root_ca ? "Root CA" : "Missing");
  target("certificates").innerHTML = `
    <dl class="dl-grid">
      <div><dt>Root CA</dt><dd>${escapeHtml(data.root_ca || "Not reported")}</dd></div>
      <div><dt>Private key exported</dt><dd>${data.private_key_exported ? "yes" : "no"}</dd></div>
    </dl>`;
}

function renderSecurityPosture(data) {
  const actions = data.actions || {};
  const consolePosture = data.console || {};
  const boundaries = data.boundaries || [];
  setText("security-mode", actions.read_only ? "Read only" : pretty(actions.mode || "unknown"));
  target("security").innerHTML = `
    <dl class="dl-grid">
      <div><dt>Bind</dt><dd>${escapeHtml(consolePosture.bind_host || "not reported")}</dd></div>
      <div><dt>Access</dt><dd>${consolePosture.local_only ? "local only" : consolePosture.lan_access ? "LAN mode" : "not reported"}</dd></div>
      <div><dt>Token</dt><dd>${consolePosture.token_required ? "required" : "local trust boundary"}</dd></div>
    </dl>
    ${boundaries.length ? `<ul class="compact-list">${boundaries.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : empty("No security boundaries reported.")}`;
}

function fallbackLifecycleActions() {
  const operations = store.status?.operations || [];
  return {
    mode: "preview_only",
    execute_endpoint: null,
    actions: operations.map((operation) => ({
      id: operation.id,
      label: operation.id,
      kind: operation.kind,
      impact: operation.impact,
      mutates: operation.impact !== "read-only",
      warning: "Backend action preview endpoint is not available yet.",
      command_preview: [],
      confirmation: { required: operation.impact === "destructive", phrase: operation.impact === "destructive" ? "shown by backend before execution" : null },
      job: { state: "not_started", message: "Preview only; no job endpoint is available." },
    })),
  };
}

function renderLifecycleActions(data) {
  const payload = data || fallbackLifecycleActions();
  const actions = payload.actions || [];
  setText("lifecycle-mode", payload.mode ? pretty(payload.mode) : "Preview only");
  if (!actions.length) {
    target("lifecycle").innerHTML = empty("No lifecycle actions are available for preview yet.");
    return;
  }
  if (!selectedLifecycleActionId || !actions.some((action) => action.id === selectedLifecycleActionId)) {
    const firstRunnable = actions.find((action) => action.resource?.scope === "application" && actionCanRun(action)) || actions.find((action) => actionCanRun(action)) || actions[0];
    selectedLifecycleActionId = firstRunnable.id;
  }
  const selected = actions.find((action) => action.id === selectedLifecycleActionId) || actions[0];
  const latestJob = latestJobForAction(selected.id);
  target("lifecycle").innerHTML = `
    <div class="lifecycle-layout">
      <div class="action-groups">${renderActionGroups(actions, selected.id)}</div>
      <div class="confirmation-box">
        <div class="row-main"><strong>${escapeHtml(selected.label || "Lifecycle action")}</strong>${pill(selected.impact || "unknown")}</div>
        <div class="selected-resource">${escapeHtml(resourceSummary(selected))}</div>
        <p>${escapeHtml(selected.warning || actionHelpText(selected))}</p>
        ${renderConfirmationControl(selected)}
        <code class="command">${actionCommandPreview(selected).length ? escapeHtml(commandLine(actionCommandPreview(selected))) : "Command preview pending backend support."}</code>
        ${renderActionButton(selected, payload)}
      </div>
      <div class="job-box">
        <div class="row-main"><strong>Job status</strong>${pill(latestJob?.status || selected.job?.state || "not_started")}</div>
        <p>${escapeHtml(latestJob?.message || selected.job?.message || "No lifecycle job has been submitted from the web console.")}</p>
        ${latestJob?.execution?.detail ? `<code class="command">${escapeHtml(latestJob.execution.detail)}</code>` : ""}
      </div>
    </div>`;
  bindLifecycleControls(payload);
}

function renderActionGroups(actions, selectedId) {
  const groups = [
    ["application", "Applications"],
    ["cluster", "Cluster"],
    ["pod", "Logs"],
    ["maintenance", "Maintenance"],
  ];
  const content = groups.map(([scope, label]) => {
    const scoped = actions.filter((action) => (action.resource?.scope || "maintenance") === scope);
    if (!scoped.length) return "";
    return `<section class="action-group"><h3>${escapeHtml(label)}</h3><ul class="action-list">${scoped.map((action) => renderActionPreview(action, action.id === selectedId)).join("")}</ul></section>`;
  }).join("");
  return content || `<ul class="action-list">${actions.map((action) => renderActionPreview(action, action.id === selectedId)).join("")}</ul>`;
}

function resourceSummary(action) {
  const resource = action.resource || {};
  const label = resource.label || resource.id || "Fortify Lab";
  const state = resource.state ? pretty(resource.state) : "available";
  const scope = resource.scope ? pretty(resource.scope) : "operation";
  return `${label} · ${scope} · ${state}`;
}
function latestJobForAction(actionId) {
  const jobs = store.operationJobs?.jobs || [];
  return jobs.find((job) => job.operation_id === actionId) || null;
}

function actionHelpText(action) {
  if (!action.mutates) return "Read-only operation. Useful for evidence collection without changing the lab.";
  if (action.execution_enabled) return "Execution is enabled. Review the command and confirmation requirements before running.";
  return "Execution is disabled until the web console is started with action execution enabled.";
}

function renderConfirmationControl(action) {
  const confirmation = action.confirmation || {};
  if (!confirmation.required) {
    return `<div class="confirmation-note">No typed confirmation required.</div>`;
  }
  return `<label class="confirmation-label" for="lifecycle-confirmation">Required phrase</label><input id="lifecycle-confirmation" type="text" placeholder="${escapeHtml(confirmation.phrase || "Enter confirmation phrase")}" autocomplete="off">`;
}

function actionCanRun(action) {
  return Boolean(action.execution_enabled || !action.mutates);
}

function renderActionButton(action, payload) {
  if (!actionCanRun(action)) {
    return `<button type="button" class="disabled-action" disabled>${payload.execute_endpoint ? "Execution unavailable" : "Preview only"}</button>`;
  }
  const label = action.mutates ? `Run ${action.label || "action"}` : action.kind === "logs" ? "View logs" : `Run ${action.label || "read-only action"}`;
  return `<button type="button" class="primary-action" data-run-lifecycle-action="${escapeHtml(action.id)}" ${lifecycleSubmitting ? "disabled" : ""}>${escapeHtml(label)}</button>`;
}

async function waitForJob(jobId) {
  if (!jobId) return null;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const data = await loadJson(`/api/operations/jobs/${encodeURIComponent(jobId)}`);
    const job = data.job;
    if (job && !["queued", "running"].includes(job.status)) return job;
    await new Promise((resolve) => window.setTimeout(resolve, 350));
  }
  return null;
}
async function submitLifecycleAction(action, payload) {
  const confirmation = document.querySelector("#lifecycle-confirmation")?.value || null;
  lifecycleSubmitting = true;
  renderLifecycleActions(store.lifecycleActions);
  try {
    const jobPayload = await postJson(payload.execute_endpoint || "/api/operations/jobs", {
      operation_id: action.id,
      execute: Boolean(action.mutates && action.execution_enabled),
      confirmation,
    });
    const finishedJob = await waitForJob(jobPayload.job?.job_id);
    const job = finishedJob || jobPayload.job;
    const existingJobs = store.operationJobs?.jobs || [];
    store.operationJobs = { jobs: [job, ...existingJobs.filter((item) => item.job_id !== job.job_id)] };
    await loadPanel("lifecycleAudit", "/api/lifecycle/audit", renderLifecycleAudit);
  } catch (error) {
    store.operationJobs = { jobs: [{ operation_id: action.id, status: "failed", message: error.message }] };
  } finally {
    lifecycleSubmitting = false;
    renderLifecycleActions(store.lifecycleActions);
  }
}

function bindLifecycleControls(payload) {
  for (const button of document.querySelectorAll("[data-lifecycle-action]")) {
    button.addEventListener("click", () => {
      selectedLifecycleActionId = button.dataset.lifecycleAction;
      renderLifecycleActions(store.lifecycleActions);
    });
  }
  const runButton = document.querySelector("[data-run-lifecycle-action]");
  if (!runButton) return;
  runButton.addEventListener("click", () => {
    const action = (payload.actions || []).find((item) => item.id === runButton.dataset.runLifecycleAction);
    if (action && actionCanRun(action)) submitLifecycleAction(action, payload);
  });
}

function actionCommandPreview(action) {
  return action.command_preview || action.command || [];
}

function renderActionPreview(action, selected = false) {
  const confirmation = action.confirmation || {};
  const commandPreview = actionCommandPreview(action);
  return `<li class="action-card ${selected ? "is-selected" : ""}">
    <button type="button" class="action-select" data-lifecycle-action="${escapeHtml(action.id)}"><span>${escapeHtml(action.label || action.id || "Lifecycle action")}</span>${pill(action.impact || "unknown")}</button>
    <div class="row-note">${escapeHtml(action.kind || "operation")} · ${action.mutates ? "mutating" : "read-only"} · ${confirmation.required ? "typed confirmation required" : "no typed confirmation"}</div>
    ${commandPreview.length ? `<code class="command">${escapeHtml(commandLine(commandPreview))}</code>` : `<div class="row-note">Command preview will appear when backend metadata is available.</div>`}
  </li>`;
}
function renderLifecycleAudit(data) {
  const entries = data.entries || [];
  setText("audit-count", `${entries.length} entries`);
  target("audit").innerHTML = entries.length
    ? `<ul class="card-list">${entries.slice(0, 6).map((entry) => `
        <li class="card-row">
          <div class="row-main"><strong>${escapeHtml(entry.action || "Lifecycle action")}</strong>${pill(entry.state || "unknown")}</div>
          <div class="row-note">${escapeHtml(entry.timestamp || "time unavailable")} · ${escapeHtml(entry.operator || "operator unknown")}</div>
        </li>`).join("")}</ul>`
    : empty(data.placeholder || "No lifecycle audit entries have been recorded yet.");
}

async function loadPanel(key, path, render) {
  try {
    const data = await loadJson(path);
    store[key] = data;
    render(data);
    return true;
  } catch (error) {
    if (key === "lifecycleActions") {
      store.lifecycleActions = fallbackLifecycleActions();
      renderLifecycleActions(store.lifecycleActions);
      return true;
    }
    if (key === "lifecycleAudit") {
      renderLifecycleAudit({ entries: [], placeholder: "Lifecycle audit endpoint is not available yet." });
      return true;
    }
    const panelMap = { config: "configuration", diagnostics: "health", deploymentStatus: "workspace", guide: "deployment", status: "summary-state", routes: "routes", securityPosture: "security" };
    fail(panelMap[key] || key, error);
    return false;
  }
}

async function refreshConsole() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    const results = await Promise.all([
      loadPanel("status", "/api/status", renderSummary),
      loadPanel("deploymentStatus", "/api/deployment/status", () => {}),
      loadPanel("guide", "/api/deployment/guide", renderDeployment),
      loadPanel("config", "/api/config", renderConfiguration),
      loadPanel("diagnostics", "/api/deployment/diagnostics", renderDiagnostics),
      loadPanel("logs", "/api/deployment/logs", renderLogs),
      loadPanel("certificates", "/api/certificates", renderCertificates),
      loadPanel("routes", "/api/routes", () => {}),
      loadPanel("services", "/api/services", () => {}),
      loadPanel("serviceHealth", "/api/services/health", () => {}),
      loadPanel("securityPosture", "/api/security/posture", renderSecurityPosture),
      loadPanel("lifecycleActions", "/api/lifecycle/actions", renderLifecycleActions),
      loadPanel("lifecycleAudit", "/api/lifecycle/audit", renderLifecycleAudit),
      loadPanel("operationJobs", "/api/operations/jobs", () => {}),
    ]);

    renderSummary();
    renderWorkspace();
    renderRoutes();
    if (store.logs) renderLogs(store.logs);
    if (store.lifecycleActions) renderLifecycleActions(store.lifecycleActions);

    const loaded = results.filter(Boolean).length;
    if (loaded === results.length) {
      state.textContent = "Connected";
      state.dataset.state = "ok";
    } else if (loaded > 0) {
      state.textContent = "Partial data";
      state.dataset.state = "partial";
    } else {
      state.textContent = "Needs attention";
      state.dataset.state = "error";
    }
  } finally {
    refreshInFlight = false;
  }
}

function scheduleRefresh() {
  refreshConsole();
  window.setInterval(refreshConsole, refreshIntervalMs);
}

setupThemeSwitch();
setupPanelFocus();
scheduleRefresh();
