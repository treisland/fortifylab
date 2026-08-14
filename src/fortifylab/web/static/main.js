const token = new URLSearchParams(window.location.search).get("token");
const refreshIntervalMs = 5000;
let refreshInFlight = false;
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
};

function headers() {
  return token ? { "X-FortifyLab-Token": token } : {};
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
          <code class="command">${escapeHtml(commandLine(pod.recent_command))}</code>
        </li>`).join("")}</ul>`
    : empty("No pod log options reported yet.");
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

async function loadPanel(key, path, render) {
  try {
    const data = await loadJson(path);
    store[key] = data;
    render(data);
    return true;
  } catch (error) {
    const panelMap = { config: "configuration", diagnostics: "health", deploymentStatus: "workspace", guide: "deployment", status: "summary-state", routes: "routes" };
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
    ]);

    renderSummary();
    renderWorkspace();
    renderRoutes();

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

scheduleRefresh();
