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
  const operations = data.operations || [];
  target("deployment").innerHTML = rows(operations.map((op) => `${op.id} <span>${op.impact}</span>`));
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
    const [status, config, routes, certs] = await Promise.all([
      loadJson("/api/status"),
      loadJson("/api/config"),
      loadJson("/api/routes"),
      loadJson("/api/certificates"),
    ]);
    renderDeployment(status);
    renderConfiguration(config);
    renderRoutes(routes);
    renderCertificates(certs);
    state.textContent = "Connected";
    state.dataset.state = "ok";
  } catch (error) {
    state.textContent = "Needs attention";
    state.dataset.state = "error";
    for (const panel of ["deployment", "configuration", "routes", "certificates"]) {
      fail(panel, error);
    }
  }
}

boot();
