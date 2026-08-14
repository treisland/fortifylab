const token = new URLSearchParams(window.location.search).get("token");
const state = document.querySelector("#connection-state");

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
  return payload.data;
}

function target(name) {
  return document.querySelector(`[data-content="${name}"]`);
}

function rows(items) {
  if (!items.length) return '<p class="empty">No items reported.</p>';
  return `<ul class="rows">${items.map((item) => `<li class="list-row">${item}</li>`).join("")}</ul>`;
}

function renderDeployment(data) {
  const steps = data.steps || [];
  target("deployment").innerHTML = steps.length
    ? `<ol class="steps">${steps.map((step) => `<li class="list-row"><span>${step.index}. ${step.label}</span><strong>${step.state}</strong></li>`).join("")}</ol>`
    : '<p class="empty">No guided deployment steps reported.</p>';
}

function renderLogs(data) {
  const resources = data.resources || [];
  const commands = [];
  for (const resource of resources) {
    for (const pod of resource.pods || []) {
      commands.push(`${pod.number}. ${pod.name} <span>${pod.recent_command.join(" ")}</span>`);
    }
  }
  target("logs").innerHTML = commands.length ? rows(commands) : '<p class="empty">No pod log options reported yet.</p>';
}

function renderDiagnostics(data) {
  const findings = data.findings || [];
  target("routes").innerHTML = findings.length
    ? rows(findings.map((finding) => `${finding.step_label}: ${finding.message} <span>${finding.severity}</span>`))
    : '<p class="empty">No deployment diagnostics reported.</p>';
}

function renderConfiguration(data) {
  const sections = data.sections || [];
  target("configuration").innerHTML = `
    <div class="metric"><span>Sections</span><strong>${sections.length}</strong></div>
    ${rows(sections.map((section) => `${section}`))}
    <p class="empty">Secrets redacted: ${data.secrets_redacted ? "yes" : "unknown"}</p>`;
}

function renderRoutes(data) {
  const findings = data.findings || [];
  target("routes").innerHTML = findings.length
    ? rows(findings.map((finding) => finding.message || JSON.stringify(finding)))
    : '<p class="empty">No route findings reported.</p>';
}

function renderCertificates(data) {
  target("certificates").innerHTML = `
    <dl>
      <div><dt>Root CA</dt><dd>${data.root_ca}</dd></div>
      <div><dt>Private key exported</dt><dd>${data.private_key_exported ? "yes" : "no"}</dd></div>
    </dl>`;
}

function fail(panel, error) {
  target(panel).innerHTML = `<p class="error">${error.message}</p>`;
}

async function boot() {
  try {
    const [guide, config, diagnostics, logs, certs] = await Promise.all([
      loadJson("/api/deployment/guide"),
      loadJson("/api/config"),
      loadJson("/api/deployment/diagnostics"),
      loadJson("/api/deployment/logs"),
      loadJson("/api/certificates"),
    ]);
    renderDeployment(guide);
    renderConfiguration(config);
    renderDiagnostics(diagnostics);
    renderLogs(logs);
    renderCertificates(certs);
    state.textContent = "Connected";
    state.dataset.state = "ok";
  } catch (error) {
    state.textContent = "Needs attention";
    state.dataset.state = "error";
    for (const panel of ["deployment", "configuration", "routes", "logs", "certificates"]) {
      fail(panel, error);
    }
  }
}

boot();
