const token = new URLSearchParams(window.location.search).get("token");
const refreshIntervalMs = 5000;
const themeStorageKey = "fortifylab.theme";
const introStorageKey = "fortifylab.operatorIntro";
let refreshInFlight = false;
let focusedPanel = null;
let focusedPlaceholder = null;
let selectedLifecycleActionId = null;
let lifecycleSubmitting = false;
let panelFocusClosing = false;
let confirmingLifecycleActionId = null;
let logWorkspace = { open: false, operationId: null, mode: "recent", tail: "120" };
let selectedHelpTopicId = "overview";
let followedLogActionId = null;
let logFollowTimer = null;
const logRequestsInFlight = new Set();
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
  guidedJourney: null,
  helpTopics: null,
  recoveryState: null,
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

function openPanelByName(panelName) {
  const panel = Array.from(document.querySelectorAll("[data-panel]")).find((item) => item.dataset.panel === panelName);
  if (panel) openFocusedPanel(panel);
}

function bindGuidedJourneyControls() {
  for (const button of document.querySelectorAll("[data-guided-panel]")) {
    button.addEventListener("click", () => openPanelByName(button.dataset.guidedPanel));
  }
}

function renderGuidedJourney(data) {
  const journey = data || {};
  const action = journey.next_action || {};
  const deployment = journey.deployment || {};
  const onboarding = journey.onboarding || {};
  const monitoring = journey.monitoring || {};
  const serviceCounts = monitoring.services || {};
  const links = journey.links || [];
  setText("guided-state", pretty(journey.state || "checking"));
  target("guided").innerHTML = `
    <div class="guided-shell">
      <div class="guided-primary">
        <div>
          <span class="guided-kicker">Next best action</span>
          <h2>${escapeHtml(action.label || "Review lab status")}</h2>
          <p>${escapeHtml(action.reason || journey.summary || "The console is gathering enough information to recommend the next step.")}</p>
        </div>
        <button type="button" class="primary-action guided-action" data-guided-panel="${escapeHtml(action.panel || "deployment")}">${escapeHtml(action.label || "Open guided timeline")}</button>
      </div>
      <div class="guided-checks" aria-label="Guided onboarding checkpoints">
        ${guidedCheck("Configuration", onboarding.configuration_ready ? "ready" : "needs attention", onboarding.env_file?.present ? "Env file found" : "Env file not confirmed", "configuration")}
        ${guidedCheck("Certificates", onboarding.certificates_ready ? "ready" : "needs attention", onboarding.root_ca ? `Root CA: ${onboarding.root_ca}` : "Root CA not reported", "certificates")}
        ${guidedCheck("Deployment", deployment.overall_state || "pending", deployment.total_steps ? `${deployment.complete_steps || 0} of ${deployment.total_steps} steps complete` : "Waiting for profile", "deployment")}
        ${guidedCheck("Monitoring", serviceCounts.total ? `${serviceCounts.up || 0}/${serviceCounts.total} up` : "waiting", serviceCounts.total ? `${serviceCounts.down || 0} down · ${serviceCounts.degraded || 0} degraded` : "No services reported", "routes")}
      </div>
      <div class="guided-links">
        ${links.map((link) => `<button type="button" class="secondary-action" data-guided-panel="${escapeHtml(link.panel)}">${escapeHtml(link.label)}</button>`).join("")}
        <button type="button" class="secondary-action" data-help-topic-button="overview">Open operator guide</button>
      </div>
    </div>`;
  bindGuidedJourneyControls();
  document.querySelector("[data-help-topic-button]")?.addEventListener("click", () => openHelpTopic("overview"));
  renderCockpitIntro();
}

function guidedCheck(label, state, detail, panel) {
  return `<button type="button" class="guided-check" data-guided-panel="${escapeHtml(panel)}">
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(pretty(state))}</strong>
    <small>${escapeHtml(detail)}</small>
  </button>`;
}

function introPreference() {
  try {
    return window.localStorage.getItem(introStorageKey) || "new";
  } catch (error) {
    return "new";
  }
}

function setIntroPreference(value) {
  try {
    window.localStorage.setItem(introStorageKey, value);
  } catch (error) {
    // First-run guidance is nice to have; do not block the console if storage is unavailable.
  }
}

function cockpitTourSteps() {
  const action = store.guidedJourney?.next_action || {};
  return [
    { id: "orient", label: "Orient", panel: "guided", detail: "Review the recommended next action and the deployment path." },
    { id: "configure", label: "Configure", panel: "configuration", detail: "Check domain, profile, URLs, credentials, and redaction status." },
    { id: "trust", label: "Trust TLS", panel: "certificates", detail: "Retrieve the root CA and verify the lab is not serving the Traefik default certificate." },
    { id: "deploy", label: "Deploy", panel: action.panel || "deployment", detail: action.reason || "Run the guided deployment and watch the active workspace." },
    { id: "observe", label: "Observe", panel: "routes", detail: "Open service links, inspect uptime checks, and jump into logs or recovery help." },
  ];
}

function activeTourIndex() {
  const actionPanel = store.guidedJourney?.next_action?.panel;
  const steps = cockpitTourSteps();
  const index = steps.findIndex((step) => step.panel === actionPanel);
  if (index >= 0) return index;
  const focused = focusStep();
  if (!focused) return 0;
  if (["failed", "blocked"].includes(focused.state)) return 4;
  if (focused.state === "in_progress") return 3;
  return 1;
}

function renderCockpitIntro(forceOpen = false) {
  const node = document.querySelector("#cockpit-intro");
  if (!node) return;
  const preference = introPreference();
  const shouldShow = forceOpen || preference !== "skipped";
  node.hidden = !shouldShow;
  if (!shouldShow) return;
  const action = store.guidedJourney?.next_action || {};
  const journeyState = store.guidedJourney?.state || "getting ready";
  const tourSteps = cockpitTourSteps();
  const activeIndex = activeTourIndex();
  const resumed = preference === "started";
  node.innerHTML = `
    <div class="intro-copy">
      <span class="eyebrow">Guided operator cockpit</span>
      <h2>${resumed ? "Resume your lab path" : "Start with confidence"}</h2>
      <p>${escapeHtml(store.guidedJourney?.summary || "Use this console to configure, deploy, monitor, recover, and launch FortifyLab services without memorizing terminal commands.")}</p>
      <div class="intro-next"><strong>Next:</strong> ${escapeHtml(action.label || "Review lab readiness")} <span>${escapeHtml(pretty(journeyState))}</span></div>
    </div>
    <ol class="intro-steps" aria-label="Operator tour steps">
      ${tourSteps.map((step, index) => `<li class="${index === activeIndex ? "is-current" : ""}"><button type="button" data-guided-panel="${escapeHtml(step.panel)}"><span>${index + 1}</span><strong>${escapeHtml(step.label)}</strong><small>${escapeHtml(step.detail)}</small></button></li>`).join("")}
    </ol>
    <div class="intro-actions">
      <button type="button" class="primary-action" data-tour-action="${resumed ? "resume" : "start"}">${resumed ? "Resume tour" : "Start tour"}</button>
      <button type="button" class="secondary-action" data-tour-action="resume">Open next step</button>
      <button type="button" class="secondary-action" data-tour-action="skip">Skip tour</button>
    </div>`;
  bindIntroControls();
}

function bindIntroControls() {
  for (const button of document.querySelectorAll("[data-tour-action]")) {
    button.addEventListener("click", () => {
      const action = button.dataset.tourAction;
      if (action === "skip") {
        setIntroPreference("skipped");
        renderCockpitIntro();
        return;
      }
      setIntroPreference("started");
      const nextPanel = store.guidedJourney?.next_action?.panel || cockpitTourSteps()[activeTourIndex()]?.panel || "guided";
      openPanelByName(nextPanel);
      renderCockpitIntro(true);
    });
  }
  bindGuidedJourneyControls();
}

function setupIntroControls() {
  document.querySelector("#open-intro")?.addEventListener("click", () => {
    setIntroPreference("started");
    renderCockpitIntro(true);
    document.querySelector("#cockpit-intro")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function fallbackHelpTopics() {
  return {
    topics: [
      {
        id: "overview",
        title: "Operator cockpit",
        summary: "Use the guided path as the deployment spine. The panels below give live status, actions, logs, docs, certificates, and recovery signals.",
        panel: "guided",
        actions: ["Open guided path", "Review active workspace", "Check health notes"],
      },
      {
        id: "service-health",
        title: "Service health and launchpad",
        summary: "Service cards combine DNS, HTTP, TLS, ingress, lifecycle, and recent uptime signals. A failed badge usually points to Health notes or Evidence queue next.",
        panel: "routes",
        actions: ["Open service URL", "Inspect health notes", "View related pod logs"],
      },
      {
        id: "logs",
        title: "Dedicated logs workspace",
        summary: "Open recent logs for a pod or follow them live while deployment continues. Use pause, refresh, copy, and download when gathering evidence.",
        panel: "logs",
        actions: ["Open Evidence queue", "Follow logs", "Download output"],
      },
      {
        id: "tls",
        title: "TLS and root CA",
        summary: "Trust the mkcert root CA on client machines and confirm the service is not serving Traefik's default certificate.",
        panel: "certificates",
        actions: ["Retrieve root CA", "Check TLS badge", "Review certificate notes"],
      },
      {
        id: "recovery",
        title: "Guided recovery",
        summary: "When deployment stalls, start with Health notes, then Evidence queue. Prefer guided repair actions over manual Kubernetes edits.",
        panel: "health",
        actions: ["Open health notes", "Inspect logs", "Refresh service checks"],
      },
    ],
  };
}

function helpTopics() {
  const topics = store.helpTopics?.topics || store.helpTopics || fallbackHelpTopics().topics;
  return Array.isArray(topics) && topics.length ? topics : fallbackHelpTopics().topics;
}

function openHelpTopic(topicId = "overview") {
  selectedHelpTopicId = topicId;
  renderHelp(store.helpTopics || fallbackHelpTopics());
  openPanelByName("help");
}

function renderHelp(data) {
  const topics = helpTopics();
  const topic = topics.find((item) => item.id === selectedHelpTopicId) || topics[0];
  selectedHelpTopicId = topic.id;
  setText("help-count", `${topics.length} topics`);
  const recovery = store.recoveryState?.next_recovery || store.recoveryState?.next_action || null;
  target("help").innerHTML = `
    <div class="help-layout">
      <div class="help-topic-list" aria-label="Help topics">
        ${topics.map((item) => `<button type="button" class="help-topic ${item.id === topic.id ? "is-selected" : ""}" data-help-topic="${escapeHtml(item.id)}"><strong>${escapeHtml(item.title || pretty(item.id))}</strong><span>${escapeHtml(item.summary || "Open this guide topic.")}</span></button>`).join("")}
      </div>
      <article class="help-reader">
        <span class="eyebrow">Contextual help</span>
        <h3>${escapeHtml(topic.title || "Operator guide")}</h3>
        <p>${escapeHtml(topic.summary || "No summary was reported for this topic yet.")}</p>
        ${Array.isArray(topic.actions) && topic.actions.length ? `<ul class="compact-list">${topic.actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
        ${recovery ? `<div class="recovery-callout"><strong>${escapeHtml(recovery.label || "Suggested recovery")}</strong><span>${escapeHtml(recovery.reason || recovery.summary || "Review the suggested recovery path before retrying.")}</span></div>` : ""}
        <div class="help-actions">
          <button type="button" class="primary-action" data-guided-panel="${escapeHtml(topic.panel || "guided")}">Open related panel</button>
          <button type="button" class="secondary-action" data-guided-panel="health">Health notes</button>
          <button type="button" class="secondary-action" data-guided-panel="logs">Evidence queue</button>
        </div>
      </article>
    </div>`;
  for (const button of document.querySelectorAll("[data-help-topic]")) {
    button.addEventListener("click", () => openHelpTopic(button.dataset.helpTopic));
  }
  bindGuidedJourneyControls();
}

function serviceLogOperationId(service) {
  const key = serviceLifecycleKey(service);
  const pods = collectLogPods(store.logs || {});
  if (!pods.length) return null;
  const aliases = {
    ssc: ["ssc"],
    lim: ["lim"],
    mysql: ["mysql"],
    postgresql: ["postgresql", "postgres"],
    scsast: ["sast", "scsast", "scancentral"],
    "scdast-core": ["dast", "scdast"],
    "scdast-scanner": ["scanner", "dast"],
  };
  const candidates = aliases[key] || [key].filter(Boolean);
  const match = pods.find((pod) => candidates.some((candidate) => [pod.name, pod.step_label, pod.step_id].join(" ").toLowerCase().includes(candidate)));
  return match?.operation_id || null;
}

function bindServiceControls() {
  for (const button of document.querySelectorAll("[data-service-log]")) {
    button.addEventListener("click", () => {
      openLogWorkspace(button.dataset.serviceLog, "recent");
      openPanelByName("logs");
    });
  }
  for (const button of document.querySelectorAll("[data-service-help]")) {
    button.addEventListener("click", () => openHelpTopic(button.dataset.serviceHelp || "service-health"));
  }
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
  const pods = collectLogPods(data);
  setText("logs-count", logWorkspace.open && logWorkspace.operationId ? "workspace open" : `${pods.length} pods`);
  target("logs").innerHTML = `
    ${renderLogWorkspace(pods)}
    ${pods.length ? `<ul class="card-list compact-log-list">${pods.slice(0, 8).map(renderLogCard).join("")}</ul>` : empty("No pod log options reported yet.")}`;
  bindLogControls();
}

function collectLogPods(data) {
  const resources = data?.resources || [];
  return resources.flatMap((resource) => (resource.pods || []).map((pod) => ({
    ...pod,
    step_label: resource.step_label,
    step_state: resource.state,
    operation_id: `logs.${pod.name}`,
  })));
}

function renderLogCard(pod) {
  const operationId = pod.operation_id;
  const active = logWorkspace.open && logWorkspace.operationId === operationId;
  const following = followedLogActionId === operationId;
  return `<li class="card-row log-card ${active ? "is-active" : ""}">
    <div class="row-main"><strong>${escapeHtml(pod.step_label || "Pod logs")}</strong><span>${escapeHtml(pod.name)}</span></div>
    <div class="row-note">${escapeHtml(pod.phase || "unknown")} · Ready ${escapeHtml(pod.ready || "0/0")}</div>
    <div class="log-actions">
      <button type="button" class="secondary-action" data-open-log-workspace="${escapeHtml(operationId)}" data-log-mode="recent">View recent logs</button>
      <button type="button" class="secondary-action" data-open-log-workspace="${escapeHtml(operationId)}" data-log-mode="follow">${following ? "Open following logs" : "Follow logs"}</button>
    </div>
  </li>`;
}

function renderLogWorkspace(pods) {
  if (!logWorkspace.open || !logWorkspace.operationId) return "";
  const pod = pods.find((item) => item.operation_id === logWorkspace.operationId);
  if (!pod) {
    stopFollowingLogs();
    return `<section class="log-workspace"><div class="log-workspace-bar"><div><span class="eyebrow">Log workspace</span><h3>Pod no longer reported</h3></div><button type="button" class="secondary-action" data-close-log-workspace>Close</button></div><p class="row-note">The selected pod is no longer present in the latest deployment evidence.</p></section>`;
  }
  const following = followedLogActionId === logWorkspace.operationId;
  const mode = following ? "follow" : logWorkspace.mode;
  const job = latestJobForAction(logWorkspace.operationId);
  const detail = job?.execution?.detail || job?.message || (following ? "Following logs; waiting for the first refresh." : "Open recent logs or refresh to load output.");
  const previousSupported = Boolean(pod.previous_command);
  return `<section class="log-workspace" aria-live="polite">
    <div class="log-workspace-bar">
      <div>
        <span class="eyebrow">Log workspace</span>
        <h3>${escapeHtml(pod.name)}</h3>
        <p>${escapeHtml(pod.step_label || "Pod logs")} · ${escapeHtml(pod.phase || "unknown")} · Ready ${escapeHtml(pod.ready || "0/0")}</p>
      </div>
      <button type="button" class="secondary-action" data-close-log-workspace>Back to evidence</button>
    </div>
    <div class="log-toolbar" role="toolbar" aria-label="Log viewer controls">
      <button type="button" class="secondary-action ${mode === "recent" ? "is-selected" : ""}" data-log-mode-select="recent">Recent</button>
      <button type="button" class="secondary-action ${mode === "follow" ? "is-selected" : ""}" data-log-mode-select="follow">${following ? "Following" : "Follow"}</button>
      <button type="button" class="secondary-action ${mode === "previous" ? "is-selected" : ""}" data-log-mode-select="previous" ${previousSupported ? "" : "disabled"}>Previous</button>
      <label class="tail-control">Tail <select data-log-tail-size><option value="120" ${logWorkspace.tail === "120" ? "selected" : ""}>120</option><option value="250" ${logWorkspace.tail === "250" ? "selected" : ""}>250</option><option value="500" ${logWorkspace.tail === "500" ? "selected" : ""}>500</option></select></label>
      <button type="button" class="secondary-action" data-refresh-log-workspace>Refresh</button>
      ${following ? `<button type="button" class="secondary-action" data-pause-log-follow>Pause follow</button>` : ""}
      <button type="button" class="secondary-action" data-copy-log-output ${job ? "" : "disabled"}>Copy</button>
      <button type="button" class="secondary-action" data-download-log-output ${job ? "" : "disabled"}>Download</button>
    </div>
    ${mode === "previous" ? renderPreviousLogNotice(previousSupported) : `<pre class="log-output log-workspace-output">${escapeHtml(detail)}</pre>`}
    <div class="row-note log-workspace-status">${escapeHtml(logWorkspaceStatusText(job, mode, logWorkspace.tail))}</div>
  </section>`;
}

function renderPreviousLogNotice(supported) {
  return `<div class="log-placeholder">${supported ? "Previous container logs are detected for this pod. Web execution for previous logs is not wired yet; recent and follow remain available here." : "Previous container logs are not advertised for this pod."}</div>`;
}

function logWorkspaceStatusText(job, mode, tail) {
  if (mode === "previous") return "Previous log mode is a workspace hook until the backend exposes previous-container log execution.";
  if (!job) return `Ready to load the most recent ${tail} log lines.`;
  const status = jobStatusLabel(job.status || "unknown");
  return `${status} · ${mode === "follow" ? "auto-refresh every 5s" : `tail ${tail}`}`;
}

function selectedLogOutput() {
  const job = latestJobForAction(logWorkspace.operationId);
  return job?.execution?.detail || job?.message || "";
}

function bindLogControls() {
  for (const button of document.querySelectorAll("[data-open-log-workspace]")) {
    button.addEventListener("click", () => openLogWorkspace(button.dataset.openLogWorkspace, button.dataset.logMode || "recent"));
  }
  document.querySelector("[data-close-log-workspace]")?.addEventListener("click", closeLogWorkspace);
  for (const button of document.querySelectorAll("[data-log-mode-select]")) {
    button.addEventListener("click", () => setLogWorkspaceMode(button.dataset.logModeSelect));
  }
  document.querySelector("[data-refresh-log-workspace]")?.addEventListener("click", () => refreshLogWorkspace());
  document.querySelector("[data-pause-log-follow]")?.addEventListener("click", () => pauseLogFollow());
  document.querySelector("[data-copy-log-output]")?.addEventListener("click", copySelectedLogOutput);
  document.querySelector("[data-download-log-output]")?.addEventListener("click", downloadSelectedLogOutput);
  document.querySelector("[data-log-tail-size]")?.addEventListener("change", (event) => {
    logWorkspace = { ...logWorkspace, tail: event.target.value || "120" };
    refreshLogWorkspace();
  });
}

function openLogWorkspace(operationId, mode = "recent") {
  if (!operationId) return;
  const normalizedMode = ["recent", "follow", "previous"].includes(mode) ? mode : "recent";
  logWorkspace = { ...logWorkspace, open: true, operationId, mode: normalizedMode };
  if (normalizedMode === "follow") {
    startFollowingLogs(operationId);
  } else {
    if (followedLogActionId === operationId) stopFollowingLogs();
    if (normalizedMode === "recent") submitReadOnlyOperation(operationId);
  }
  if (store.logs) renderLogs(store.logs);
}

function closeLogWorkspace() {
  stopFollowingLogs();
  logWorkspace = { ...logWorkspace, open: false, operationId: null, mode: "recent" };
  if (store.logs) renderLogs(store.logs);
}

function setLogWorkspaceMode(mode) {
  if (!logWorkspace.operationId) return;
  openLogWorkspace(logWorkspace.operationId, mode);
}

function refreshLogWorkspace() {
  if (!logWorkspace.operationId || logWorkspace.mode === "previous") {
    if (store.logs) renderLogs(store.logs);
    return;
  }
  submitReadOnlyOperation(logWorkspace.operationId);
}

function startFollowingLogs(operationId) {
  stopFollowingLogs();
  followedLogActionId = operationId;
  submitReadOnlyOperation(operationId);
  logFollowTimer = window.setInterval(() => submitReadOnlyOperation(operationId), refreshIntervalMs);
}

function pauseLogFollow() {
  stopFollowingLogs();
  logWorkspace = { ...logWorkspace, mode: "recent" };
  if (store.logs) renderLogs(store.logs);
}

function stopFollowingLogs() {
  if (logFollowTimer) window.clearInterval(logFollowTimer);
  logFollowTimer = null;
  followedLogActionId = null;
}

async function copySelectedLogOutput() {
  const output = selectedLogOutput();
  if (!output || !navigator.clipboard) return;
  await navigator.clipboard.writeText(output);
}

function downloadSelectedLogOutput() {
  const output = selectedLogOutput();
  if (!output) return;
  const safeName = (logWorkspace.operationId || "logs").replace(/[^a-zA-Z0-9.-]+/g, "-");
  const blob = new Blob([output], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeName}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function submitReadOnlyOperation(operationId) {
  if (!operationId || logRequestsInFlight.has(operationId)) return;
  logRequestsInFlight.add(operationId);
  try {
    const jobPayload = await postJson("/api/operations/jobs", { operation_id: operationId });
    const finishedJob = await waitForJob(jobPayload.job?.job_id);
    const job = finishedJob || jobPayload.job;
    const existingJobs = store.operationJobs?.jobs || [];
    store.operationJobs = { jobs: [job, ...existingJobs.filter((item) => item.job_id !== job.job_id)] };
  } catch (error) {
    store.operationJobs = { jobs: [{ operation_id: operationId, status: "failed", message: error.message }] };
  } finally {
    logRequestsInFlight.delete(operationId);
    if (store.logs) renderLogs(store.logs);
    if (store.lifecycleActions) renderLifecycleActions(store.lifecycleActions);
    renderHelp(store.helpTopics || fallbackHelpTopics());
    renderCockpitIntro();
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
      const lifecycle = lifecycleHintForService(service);
      const displayState = lifecycle?.state || state;
      const history = uptimeHistory(displayState, service.service_id);
      return `<li class="service-card">
        <div class="row-main"><strong>${escapeHtml(service.label || service.service_id || "Service")}</strong>${pill(displayState)}</div>
        ${service.url ? `<a href="${escapeHtml(service.url)}" target="_blank" rel="noreferrer">${escapeHtml(service.url)}</a>` : `<span class="row-note">No URL reported.</span>`}
        <div class="uptime-strip" aria-label="${escapeHtml(service.label || service.service_id || "Service")} health history">${history.map((entry) => `<span data-state="${escapeHtml(entry)}"></span>`).join("")}</div>
        <div class="service-meta">
          ${checkPill(service, "dns")}
          ${checkPill(service, "http")}
          ${checkPill(service, "tls")}
          ${checkPill(service, "ingress")}
        </div>
        ${renderServiceHint(service, lifecycle)}
        ${renderServiceActions(service)}
      </li>`;
    }).join("")}</ul>`;
    bindServiceControls();
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
      <div class="service-actions"><button type="button" class="secondary-action" data-service-help="service-health">Explain status</button></div>
    </li>`;
  }).join("")}</ul>`;
  bindServiceControls();
}

function serviceState(service) {
  const checks = Object.values(service.checks || {});
  if (!checks.length) return "unknown";
  if (checks.some((check) => check.state === "blocked")) return "down";
  if (checks.some((check) => check.state === "warning")) return "degraded";
  if (checks.every((check) => check.state === "ok")) return "up";
  return "unknown";
}

function lifecycleHintForService(service) {
  const key = serviceLifecycleKey(service);
  if (!key) return null;
  const record = latestLifecycleRecordForKey(key);
  if (!record) return null;
  const status = String(record.status || record.state || "").toLowerCase();
  const action = record.lifecycle_action;
  const complete = status === "complete";
  if (["failed", "rejected"].includes(status)) {
    return {
      state: "action failed",
      title: "Recent lifecycle action failed",
      message: `${record.label} did not complete. Review Action Audit before retrying.`,
    };
  }
  if (["queued", "running"].includes(status)) {
    return {
      state: "changing",
      title: "Lifecycle action in progress",
      message: `${record.label} is ${status}. Service health will refresh when the action finishes.`,
    };
  }
  if (complete && action === "destroy") {
    return {
      state: "expected-not-deployed",
      title: "Intentionally destroyed",
      message: `${record.resourceLabel} was destroyed from lifecycle controls. Start it again to recreate the deployment.`,
    };
  }
  if (complete && action === "stop") {
    return {
      state: "expected-stopped",
      title: key === "cluster" ? "Lab intentionally stopped" : "Intentionally stopped",
      message: `${record.resourceLabel} was stopped from lifecycle controls. Start it again when you are ready.`,
    };
  }
  if (complete && action === "start") {
    return {
      state: null,
      title: "Recently started",
      message: `${record.resourceLabel} was started from lifecycle controls. Monitoring is verifying readiness.`,
    };
  }
  return null;
}

function serviceLifecycleKey(service) {
  const values = [
    service.service_id,
    service.label,
    service.host,
    service.url,
    Object.values(service.checks || {}).map((check) => check.message || "").join(" "),
  ].join(" ").toLowerCase();
  const aliases = [
    ["ssc", ["ssc", "software security center", "ssc-webapp"]],
    ["lim", ["lim", "license and infrastructure manager"]],
    ["mysql", ["mysql"]],
    ["postgresql", ["postgresql", "postgres"]],
    ["scsast", ["scsast", "scancentral sast", "sast controller"]],
    ["scdast-core", ["scdast-core", "scancentral dast", "dast core", "dast"]],
    ["scdast-scanner", ["scdast-scanner", "dast scanner"]],
  ];
  const match = aliases.find(([, names]) => names.some((name) => values.includes(name)));
  return match ? match[0] : null;
}

function latestLifecycleRecordForKey(key) {
  const records = lifecycleRecords()
    .filter((record) => recordMatchesLifecycleKey(record, key) || recordMatchesLifecycleKey(record, "cluster"))
    .sort((left, right) => lifecycleRecordTime(right) - lifecycleRecordTime(left));
  return records[0] || null;
}

function lifecycleRecords() {
  const jobs = (store.operationJobs?.jobs || []).map((job) => lifecycleRecordFromJob(job));
  const audit = (store.lifecycleAudit?.entries || []).map((entry) => lifecycleRecordFromAudit(entry));
  return [...jobs, ...audit].filter(Boolean);
}

function lifecycleRecordFromJob(job) {
  const parsed = parseLifecycleOperation(job.operation_id);
  if (!parsed) return null;
  return {
    ...parsed,
    status: job.status,
    timestamp: job.finished_at || job.started_at || job.created_at || job.timestamp,
    label: job.action_label || friendlyLifecycleLabel(parsed),
    resourceLabel: job.resource || parsed.resourceLabel,
  };
}

function lifecycleRecordFromAudit(entry) {
  const parsed = parseLifecycleOperation(entry.operation_id);
  if (!parsed) return null;
  return {
    ...parsed,
    status: entry.status || entry.state,
    timestamp: entry.timestamp,
    label: entry.action_label || friendlyLifecycleLabel(parsed),
    resourceLabel: entry.resource || parsed.resourceLabel,
  };
}

function parseLifecycleOperation(operationId) {
  const parts = String(operationId || "").split(".");
  if (parts[0] === "app" && parts.length >= 3) {
    return { scope: "application", resourceKey: parts[1], lifecycle_action: parts[2], resourceLabel: pretty(parts[1]) };
  }
  if (parts[0] === "cluster" && parts.length >= 2) {
    return { scope: "cluster", resourceKey: "cluster", lifecycle_action: parts[1], resourceLabel: "MicroK8s cluster" };
  }
  return null;
}

function recordMatchesLifecycleKey(record, key) {
  if (!record) return false;
  if (key === "cluster") return record.resourceKey === "cluster";
  return record.resourceKey === key;
}

function lifecycleRecordTime(record) {
  const time = Date.parse(record?.timestamp || "");
  return Number.isFinite(time) ? time : 0;
}

function friendlyLifecycleLabel(record) {
  return `${pretty(record.lifecycle_action || "Lifecycle")} ${record.resourceLabel || "resource"}`;
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

function renderServiceHint(service, lifecycle) {
  if (lifecycle) {
    return `<div class="service-lifecycle-note"><strong>${escapeHtml(lifecycle.title)}</strong><span>${escapeHtml(lifecycle.message)}</span></div>`;
  }
  const hint = (service.hints || [])[0];
  if (!hint) return "";
  return `<div class="row-note">${escapeHtml(hint.message || "Health check needs attention.")}</div>`;
}

function renderServiceActions(service) {
  const logOperationId = serviceLogOperationId(service);
  const state = serviceState(service);
  const topic = state === "up" ? "service-health" : state === "degraded" ? "recovery" : state === "down" ? "recovery" : "service-health";
  return `<div class="service-actions">
    ${logOperationId ? `<button type="button" class="secondary-action" data-service-log="${escapeHtml(logOperationId)}">Open logs</button>` : `<button type="button" class="secondary-action" data-guided-panel="logs">Evidence queue</button>`}
    <button type="button" class="secondary-action" data-service-help="${escapeHtml(topic)}">Explain status</button>
  </div>`;
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
      confirmation: { required: operation.impact === "destructive", phrase: operation.impact === "destructive" ? "shown by backend before execution" : null },
      job: { state: "not_started", message: "Preview only; no job endpoint is available." },
    })),
  };
}

function renderLifecycleActions(data) {
  const payload = data || fallbackLifecycleActions();
  const actions = (payload.actions || []).filter((action) => action.resource?.scope !== "pod");
  const modeLabel = payload.mode ? pretty(payload.mode) : "Preview only";
  setText("lifecycle-mode", modeLabel);
  if (!actions.length) {
    target("lifecycle").innerHTML = empty("No lifecycle actions are available for preview yet.");
    return;
  }
  target("lifecycle").innerHTML = `
    <div class="lifecycle-layout">
      ${renderActionGroups(actions, payload)}
    </div>`;
  bindLifecycleControls(payload);
}

function renderActionGroups(actions, payload) {
  const labActions = actions.filter((action) => ["cluster", "maintenance"].includes(action.resource?.scope || "maintenance"));
  const appActions = actions.filter((action) => action.resource?.scope === "application");
  return `
    <section class="action-group lab-controls">
      <div class="section-heading"><h3>Overall lab controls</h3><span>${escapeHtml(payload.mode ? pretty(payload.mode) : "Preview only")}</span></div>
      <div class="control-grid compact-controls">${labActions.length ? labActions.map((action) => renderActionPreview(action, payload)).join("") : empty("No lab-level actions are available.")}</div>
    </section>
    <section class="action-group deployment-controls">
      <div class="section-heading"><h3>Individual deployment controls</h3><span>${appActions.length} actions</span></div>
      <div class="control-grid">${appActions.length ? appActions.map((action) => renderActionPreview(action, payload)).join("") : empty("No deployment-level actions are available yet.")}</div>
    </section>`;
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
  if (action.execution_enabled) return "Execution is enabled for this action.";
  return "Execution is disabled until the web console is started with action execution enabled.";
}

function renderConfirmationControl(action) {
  const confirmation = action.confirmation || {};
  if (!confirmation.required) {
    return `<div class="confirmation-note">No typed confirmation required.</div>`;
  }
  if (confirmingLifecycleActionId !== action.id) {
    return `<div class="confirmation-note guarded-note">Destructive action. Review impact before continuing.</div>`;
  }
  return renderGuardedConfirmation(action);
}

function actionCanRun(action) {
  return Boolean(action.execution_enabled || !action.mutates);
}

function renderActionButton(action, payload) {
  if (!actionCanRun(action)) {
    return `<button type="button" class="disabled-action" disabled>${payload.execute_endpoint ? "Execution unavailable" : "Preview only"}</button>`;
  }
  if (action.confirmation?.required) {
    if (confirmingLifecycleActionId === action.id) return "";
    return `<button type="button" class="secondary-action guarded-action" data-open-lifecycle-confirmation="${escapeHtml(action.id)}" ${lifecycleSubmitting ? "disabled" : ""}>Review ${escapeHtml(action.label || "destructive action")}</button>`;
  }
  const label = action.mutates ? `Run ${action.label || "action"}` : action.kind === "logs" ? "View logs" : `Run ${action.label || "read-only action"}`;
  return `<button type="button" class="primary-action" data-run-lifecycle-action="${escapeHtml(action.id)}" ${lifecycleSubmitting ? "disabled" : ""}>${escapeHtml(label)}</button>`;
}

function mergeOperationJob(job) {
  if (!job) return null;
  const existingJobs = store.operationJobs?.jobs || [];
  store.operationJobs = { jobs: [job, ...existingJobs.filter((item) => item.job_id !== job.job_id)] };
  return job;
}

function isTerminalJob(job) {
  return Boolean(job && !["queued", "running"].includes(job.status));
}

async function waitForJob(jobId, options = {}) {
  if (!jobId) return null;
  const attempts = options.attempts ?? 120;
  const delayMs = options.delayMs ?? 1000;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const data = await loadJson(`/api/operations/jobs/${encodeURIComponent(jobId)}`);
    const job = data.job;
    if (job) {
      mergeOperationJob(job);
      if (typeof options.onUpdate === "function") options.onUpdate(job);
      if (isTerminalJob(job)) return job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, delayMs));
  }
  return latestJobById(jobId);
}
function latestJobById(jobId) {
  const jobs = store.operationJobs?.jobs || [];
  return jobs.find((job) => job.job_id === jobId) || null;
}

async function refreshOperationSurface() {
  await refreshConsole({ force: true });
}

async function submitLifecycleAction(action, payload, confirmed = false) {
  const confirmation = confirmationValueFor(action, confirmed);
  lifecycleSubmitting = true;
  confirmingLifecycleActionId = null;
  renderLifecycleActions(store.lifecycleActions);
  try {
    const jobPayload = await postJson(payload.execute_endpoint || "/api/operations/jobs", {
      operation_id: action.id,
      execute: Boolean(action.mutates && action.execution_enabled),
      confirmation,
    });
    const queuedJob = mergeOperationJob(jobPayload.job);
    renderLifecycleActions(store.lifecycleActions);
    await loadPanel("lifecycleAudit", "/api/lifecycle/audit", renderLifecycleAudit);
    const finishedJob = await waitForJob(queuedJob?.job_id, {
      onUpdate: () => {
        if (store.lifecycleActions) renderLifecycleActions(store.lifecycleActions);
      },
    });
    mergeOperationJob(finishedJob || queuedJob);
    await refreshOperationSurface();
  } catch (error) {
    mergeOperationJob({ operation_id: action.id, status: "failed", message: error.message });
    await loadPanel("lifecycleAudit", "/api/lifecycle/audit", renderLifecycleAudit);
    await refreshOperationSurface();
  } finally {
    lifecycleSubmitting = false;
    if (store.lifecycleActions) renderLifecycleActions(store.lifecycleActions);
    renderHelp(store.helpTopics || fallbackHelpTopics());
    renderCockpitIntro();
  }
}

function bindLifecycleControls(payload) {
  for (const openButton of document.querySelectorAll("[data-open-lifecycle-confirmation]")) {
    openButton.addEventListener("click", () => {
      confirmingLifecycleActionId = openButton.dataset.openLifecycleConfirmation;
      renderLifecycleActions(store.lifecycleActions);
    });
  }
  for (const cancelButton of document.querySelectorAll("[data-cancel-lifecycle-confirmation]")) {
    cancelButton.addEventListener("click", () => {
      if (confirmingLifecycleActionId === cancelButton.dataset.cancelLifecycleConfirmation) {
        confirmingLifecycleActionId = null;
      }
      renderLifecycleActions(store.lifecycleActions);
    });
  }
  for (const confirmButton of document.querySelectorAll("[data-confirm-lifecycle-action]")) {
    confirmButton.addEventListener("click", () => {
      const action = (payload.actions || []).find((item) => item.id === confirmButton.dataset.confirmLifecycleAction);
      if (action && actionCanRun(action)) submitLifecycleAction(action, payload, true);
    });
  }
  for (const runButton of document.querySelectorAll("[data-run-lifecycle-action]")) {
    runButton.addEventListener("click", () => {
      const action = (payload.actions || []).find((item) => item.id === runButton.dataset.runLifecycleAction);
      if (action && actionCanRun(action)) submitLifecycleAction(action, payload);
    });
  }
}

function renderActionPreview(action, payload) {
  const confirmation = action.confirmation || {};
  const latestJob = latestJobForAction(action.id);
  const resource = action.resource || {};
  const confirming = confirmation.required && confirmingLifecycleActionId === action.id;
  return `<article class="action-card ${action.impact === "destructive" ? "is-destructive" : ""} ${confirming ? "is-confirming" : ""}">
    <div class="action-card-top">
      <div>
        <h4>${escapeHtml(action.label || action.id || "Lifecycle action")}</h4>
        <div class="row-note">${escapeHtml(resourceSummary(action))}</div>
      </div>
      ${pill(action.impact || "unknown")}
    </div>
    <p>${escapeHtml(action.warning || actionHelpText(action))}</p>
    ${renderConfirmationControl(action)}
    <div class="action-footer">
      ${renderActionButton(action, payload)}
      ${latestJob ? `<span class="inline-job-state" data-state="${escapeHtml(latestJob.status || "submitted")}">${escapeHtml(jobStatusLabel(latestJob))}</span>` : ""}
    </div>
    ${latestJob ? `<div class="inline-job-message">${escapeHtml(jobDisplayMessage(latestJob))}</div>` : ""}
  </article>`;
}

function renderGuardedConfirmation(action) {
  const label = action.label || "destructive action";
  const resource = action.resource?.label || action.resource?.id || "this resource";
  const warning = action.warning || "This can remove deployed resources and may delete data. Use it only when you intend to rebuild or recover the service.";
  return `<div class="guarded-confirmation" role="group" aria-label="Confirm ${escapeHtml(label)}">
    <div>
      <strong>Confirm ${escapeHtml(label)}</strong>
      <p>${escapeHtml(warning)}</p>
      <span>Target: ${escapeHtml(resource)}</span>
    </div>
    <div class="guarded-actions">
      <button type="button" class="secondary-action" data-cancel-lifecycle-confirmation="${escapeHtml(action.id)}">Cancel</button>
      <button type="button" class="danger-action" data-confirm-lifecycle-action="${escapeHtml(action.id)}" ${lifecycleSubmitting ? "disabled" : ""}>Confirm</button>
    </div>
  </div>`;
}

function confirmationValueFor(action, confirmed) {
  const confirmation = action.confirmation || {};
  if (!confirmation.required) return null;
  return confirmed ? confirmation.phrase || null : null;
}

function domId(value) {
  return String(value || "action").replace(/[^a-zA-Z0-9_-]/g, "-");
}

function jobStatusLabel(job) {
  const status = String(job?.status || "submitted");
  const labels = { queued: "Queued", running: "Running", complete: "Complete", failed: "Failed", rejected: "Rejected" };
  return labels[status] || pretty(status);
}

function jobDisplayMessage(job) {
  const statusMessages = {
    queued: "Operation queued and waiting to start.",
    running: "Operation is running. Live status will refresh when it finishes.",
    complete: "Operation completed. Live status has been refreshed.",
    failed: "Operation failed. Review the audit entry and logs for details.",
    rejected: "Operation was rejected before execution.",
  };
  const message = job.execution?.detail || job.message || statusMessages[job.status] || "Operation submitted.";
  return message.replace(/(?:\.\/)?(?:apps|scripts)\/[^\s'"]+/g, "[operation]");
}
function renderLifecycleAudit(data) {
  const entries = data.entries || [];
  setText("audit-count", `${entries.length} entries`);
  target("audit").innerHTML = entries.length
    ? `<ul class="card-list audit-list">${entries.slice(0, 6).map((entry) => {
        const title = entry.action_label || friendlyAuditAction(entry.action, entry.operation_id);
        const resource = entry.resource ? ` · ${entry.resource}` : "";
        const duration = formatDuration(entry.duration_seconds);
        const meta = [entry.timestamp || "time unavailable", entry.operator || "web console", duration].filter(Boolean).join(" · ");
        const detail = entry.summary || entry.message || "No execution summary reported.";
        return `
        <li class="card-row audit-row">
          <div class="row-main"><strong>${escapeHtml(title)}</strong>${pill(entry.status || entry.state || "unknown")}</div>
          <div class="row-note">${escapeHtml(meta)}${escapeHtml(resource)}</div>
          <div class="row-note">${escapeHtml(detail)}</div>
        </li>`;
      }).join("")}</ul>`
    : empty(data.placeholder || "No lifecycle audit entries have been recorded yet.");
}

function friendlyAuditAction(action, operationId) {
  if (operationId) return pretty(operationId.replace(/^app\./, "").replace(/\./g, " "));
  return pretty(String(action || "Lifecycle action").replace(/^job\./, ""));
}

function formatDuration(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(1)}s`;
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
    const panelMap = { config: "configuration", diagnostics: "health", deploymentStatus: "workspace", guide: "deployment", guidedJourney: "guided", status: "summary-state", routes: "routes", securityPosture: "security" };
    fail(panelMap[key] || key, error);
    return false;
  }
}

async function loadOptionalPanel(key, path, render, fallback) {
  try {
    const data = await loadJson(path);
    store[key] = data;
    render(data);
    return true;
  } catch (error) {
    const data = typeof fallback === "function" ? fallback() : fallback;
    store[key] = data;
    render(data);
    return true;
  }
}

async function refreshConsole(options = {}) {
  if (refreshInFlight) {
    if (!options.force) return false;
    for (let attempt = 0; attempt < 20 && refreshInFlight; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 150));
    }
    if (refreshInFlight) return false;
  }
  refreshInFlight = true;
  try {
    const results = await Promise.all([
      loadPanel("status", "/api/status", renderSummary),
      loadPanel("guidedJourney", "/api/guided/journey", renderGuidedJourney),
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
      loadOptionalPanel("helpTopics", "/api/help/topics", renderHelp, fallbackHelpTopics),
      loadOptionalPanel("recoveryState", "/api/recovery/state", () => renderHelp(store.helpTopics || fallbackHelpTopics()), () => ({})),
    ]);

    renderSummary();
    renderWorkspace();
    renderRoutes();
    if (store.logs) renderLogs(store.logs);
    if (store.lifecycleActions) renderLifecycleActions(store.lifecycleActions);
    renderHelp(store.helpTopics || fallbackHelpTopics());
    renderCockpitIntro();

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
    return loaded === results.length;
  } finally {
    refreshInFlight = false;
  }
}

function scheduleRefresh() {
  refreshConsole();
  window.setInterval(refreshConsole, refreshIntervalMs);
}

setupThemeSwitch();
setupIntroControls();
setupPanelFocus();
renderHelp(fallbackHelpTopics());
renderCockpitIntro();
scheduleRefresh();
