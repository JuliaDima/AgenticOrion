const state = {
  workflow: null,
  packets: [],
  runs: [],
  current: null,
  selectedAgent: null,
  staticMode: false,
};

const $ = (id) => document.getElementById(id);
const STATIC_DATA_ROOT = "static-data";

function fmtMs(ms) {
  if (!ms && ms !== 0) return "--";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function fmtNum(value, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "--";
}

function fmtCost(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "--";
  if (n < 0.01) return `$${n.toFixed(5)}`;
  return `$${n.toFixed(2)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function scorePercent(value) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n * 100)) : 0;
}

function staticDataUrl(url) {
  if (url === "/api/workflow") return `${STATIC_DATA_ROOT}/workflow.json`;
  if (url === "/api/packets") return `${STATIC_DATA_ROOT}/packets.json`;
  if (url === "/api/runs") return `${STATIC_DATA_ROOT}/runs.json`;
  if (url.startsWith("/api/runs/")) {
    return `${STATIC_DATA_ROOT}/runs/${encodeURIComponent(url.split("/").pop())}.json`;
  }
  return null;
}

async function fetchJson(url, options) {
  const useStaticOnly = window.location.hostname.endsWith("github.io");
  const fallbackUrl = staticDataUrl(url);
  const requestUrl = useStaticOnly && fallbackUrl && !options ? fallbackUrl : url;

  try {
    if (useStaticOnly && fallbackUrl && !options) state.staticMode = true;
    const res = await fetch(requestUrl, options);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  } catch (err) {
    if (!options && fallbackUrl && requestUrl !== fallbackUrl) {
      state.staticMode = true;
      const res = await fetch(fallbackUrl);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      return data;
    }
    throw err;
  }
}

async function init() {
  drawSky();
  state.workflow = await fetchJson("/api/workflow");
  state.packets = await fetchJson("/api/packets");
  populatePackets();
  await refreshRuns();
  bindEvents();
  if (state.runs[0]) {
    await loadRun(state.runs[0].run_id);
  } else {
    renderWorkflow();
  }
}

function bindEvents() {
  $("runButton").addEventListener("click", runSelectedPacket);
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      $(button.dataset.tab).classList.add("active");
    });
  });
}

function populatePackets() {
  $("packetSelect").innerHTML = state.packets
    .map((packet) => {
      const label = `P${String(packet.index).padStart(2, "0")} | ${packet.mission}`;
      return `<option value="${packet.index}">${escapeHtml(label)}</option>`;
    })
    .join("");
}

async function refreshRuns() {
  state.runs = await fetchJson("/api/runs");
  renderRunList();
}

function renderRunList() {
  const currentId = state.current?.run?.run_id;
  $("runList").innerHTML = state.runs
    .map((run) => {
      const active = run.run_id === currentId ? " active" : "";
      const score = run.interest_score !== null && run.interest_score !== undefined ? `interest ${fmtNum(run.interest_score)}` : "summary only";
      const tokens = run.total_tokens ? ` | ${Number(run.total_tokens).toLocaleString()} tok` : "";
      return `
        <button class="run-item${active}" data-run="${escapeHtml(run.run_id)}">
          <strong>${escapeHtml(run.object_id || run.query || "Run")}</strong>
          <span>${escapeHtml(run.status)} | ${fmtMs(run.duration_ms)} | ${escapeHtml(score)}${tokens}</span>
        </button>
      `;
    })
    .join("");
  document.querySelectorAll(".run-item").forEach((item) => {
    item.addEventListener("click", () => loadRun(item.dataset.run));
  });
}

async function loadRun(runId) {
  state.current = await fetchJson(`/api/runs/${runId}`);
  state.selectedAgent = state.current.agents.find((agent) => agent.id === "evidence_aggregator") || state.current.agents[0];
  renderAll();
}

async function runSelectedPacket() {
  if (state.staticMode || window.location.hostname.endsWith("github.io")) {
    $("runStatus").textContent = "GitHub Pages is static. Run packets from the local dashboard.";
    return;
  }
  const packetIndex = Number($("packetSelect").value || 1);
  $("runButton").disabled = true;
  $("runStatus").textContent = "Running workflow. This can take about a minute.";
  try {
    state.current = await fetchJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ packet_index: packetIndex }),
    });
    await refreshRuns();
    state.selectedAgent = state.current.agents.find((agent) => agent.id === "evidence_aggregator") || state.current.agents[0];
    renderAll();
    $("runStatus").textContent = "Run complete.";
  } catch (err) {
    $("runStatus").textContent = err.message;
  } finally {
    $("runButton").disabled = false;
  }
}

function renderAll() {
  renderRunList();
  renderHeader();
  renderWorkflow();
  renderInspector(state.selectedAgent);
  renderScience();
  renderPerformance();
  renderData();
  renderReport();
}

function renderHeader() {
  const current = state.current;
  const packet = current.packet || {};
  const run = current.run || {};
  const metrics = current.metrics || {};
  const agg = current.state?.aggregated_evidence || {};
  const novel = current.state?.novelty_rarity_assessment || {};
  const verdict = agg.triage_verdict || run.triage_verdict || "Trace summary";
  const interest = agg.overall_interest_score ?? novel.overall_interest_score ?? run.interest_score;

  $("objectTitle").textContent = `${run.object_id || "Observation"} | ${packet.experiment_type || "workflow run"}`;
  $("statusPill").textContent = run.status || "idle";
  $("missionLabel").textContent = packet.mission || run.query || "Mission";
  $("verdictLabel").textContent = verdict;
  $("summaryLabel").textContent = packet.short_summary || metrics.metric_note || "Existing database trace without full final state. Run a packet from the dashboard to persist complete structured outputs.";
  $("interestMetric").textContent = interest !== null && interest !== undefined ? fmtNum(Number(interest)) : "--";
  $("wallMetric").textContent = fmtMs(metrics.total_wall_ms || run.duration_ms);
  $("speedMetric").textContent = metrics.speedup ? `${fmtNum(metrics.speedup)}x` : "--";
  $("tokenMetric").textContent = metrics.total_tokens !== null && metrics.total_tokens !== undefined
    ? `${metrics.total_tokens.toLocaleString()} tok · ${fmtCost(metrics.estimated_cost_usd)}`
    : (run.status === "running" ? "pending" : (metrics.consumption_note ? "not logged" : "--"));
}

const graphPositions = {
  START: [40, 260],
  supervisor: [170, 245],
  observation_characterizer: [365, 245],
  astrophysical_interpreter: [610, 70],
  artefact_checker: [610, 190],
  novelty_assessor: [610, 310],
  context_retriever: [610, 430],
  evidence_aggregator: [845, 245],
  followup_prioritizer: [1035, 185],
  code_executor: [1035, 335],
  synthesis: [1035, 455],
};

function renderWorkflow() {
  const svg = $("agentGraph");
  const agents = state.current?.agents || state.workflow?.agents || [];
  const byId = Object.fromEntries(agents.map((agent) => [agent.id, agent]));
  const edgeMarkup = (state.workflow?.edges || [])
    .map(([from, to]) => {
      const [x1, y1] = graphPositions[from] || [0, 0];
      const [x2, y2] = graphPositions[to] || [0, 0];
      const strong = ["astrophysical_interpreter", "artefact_checker", "novelty_assessor", "context_retriever"].includes(from);
      const cls = strong ? "edge influence-strong" : "edge";
      return `<path class="${cls}" d="M ${x1 + 120} ${y1 + 42} C ${x1 + 175} ${y1 + 42}, ${x2 - 45} ${y2 + 42}, ${x2} ${y2 + 42}" />`;
    })
    .join("");

  const nodes = [
    { id: "START", label: "START", role: "packet", group: "start" },
    ...agents,
  ];

  const nodeMarkup = nodes
    .filter((node) => graphPositions[node.id])
    .map((node) => {
      const [x, y] = graphPositions[node.id];
      const active = state.selectedAgent?.id === node.id ? " active" : "";
      const timing = node.id === "START" ? "" : fmtMs(byId[node.id]?.timing?.duration_ms || byId[node.id]?.call?.duration_ms);
      const sub = node.id === "START" ? "input packet" : node.group;
      return `
        <g class="node-card${active}" data-agent="${escapeHtml(node.id)}" transform="translate(${x}, ${y})">
          <rect width="178" height="84"></rect>
          <text class="node-title" x="16" y="30">${escapeHtml(node.label || node.id)}</text>
          <text class="node-sub" x="16" y="52">${escapeHtml(sub || "")}</text>
          <text class="node-time" x="16" y="72">${escapeHtml(timing)}</text>
        </g>
      `;
    })
    .join("");

  svg.innerHTML = `
    <defs>
      <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
        <path d="M0,0 L0,6 L9,3 z" fill="#7d8a96"></path>
      </marker>
    </defs>
    <g marker-end="url(#arrow)">${edgeMarkup}</g>
    ${nodeMarkup}
  `;

  svg.querySelectorAll(".node-card").forEach((node) => {
    node.addEventListener("click", () => {
      const agent = state.current?.agents?.find((item) => item.id === node.dataset.agent);
      if (agent) {
        state.selectedAgent = agent;
        renderWorkflow();
        renderInspector(agent);
      }
    });
  });
}

function renderInspector(agent) {
  if (!agent) return;
  const call = agent.call || {};
  const tokens = agent.tokens || {};
  const timing = agent.timing || {};
  const outputs = agent.outputs || {};
  const influence = getInfluence(agent.id);
  $("agentInspector").innerHTML = `
    <p class="eyebrow">${escapeHtml(agent.group || "agent")}</p>
    <h3>${escapeHtml(agent.label || agent.id)}</h3>
    <p class="muted">${escapeHtml(agent.role || "")}</p>
    <div class="inspector-section">
      <h4>Trace</h4>
      ${kv("Started", shortTime(call.start_time || timing.timestamp))}
      ${kv("Duration", fmtMs(call.duration_ms || timing.duration_ms))}
      ${kv("Status", call.error ? "error" : "ok")}
      ${kv("Input", call.input_summary || "No call summary available")}
      ${kv("Output", call.output_summary || "No output summary available")}
    </div>
    <div class="inspector-section">
      <h4>Consumption</h4>
      ${kv("Input tokens", tokens.input_tokens?.toLocaleString?.() || "0")}
      ${kv("Output tokens", tokens.output_tokens?.toLocaleString?.() || "0")}
      ${kv("Total tokens", tokens.total_tokens?.toLocaleString?.() || "0")}
      ${kv("Influence", `${fmtNum(influence)} / 1.00`)}
    </div>
    <div class="inspector-section">
      <h4>Structured Output</h4>
      <pre class="json-block">${escapeHtml(JSON.stringify(outputs, null, 2) || "{}")}</pre>
    </div>
    <div class="inspector-section">
      <h4>Tools</h4>
      ${renderToolList(agent.tools || [])}
    </div>
  `;
}

function kv(label, value) {
  return `<div class="kv-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderToolList(tools) {
  if (!tools.length) return `<p class="muted">No tool calls recorded.</p>`;
  return tools
    .map((tool) => `
      <div class="trace-line">
        <span>${escapeHtml(tool.tool_name)}</span>
        <strong>${fmtMs(tool.duration_ms)}${tool.error ? " | error" : ""}</strong>
      </div>
    `)
    .join("");
}

function shortTime(value) {
  if (!value) return "--";
  return String(value).split("T").pop().slice(0, 12);
}

function getInfluence(agentId) {
  const st = state.current?.state || {};
  const agg = st.aggregated_evidence || {};
  const astro = st.astrophysical_interpretation || {};
  const art = st.artefact_assessment || {};
  const nov = st.novelty_rarity_assessment || {};
  const ctx = st.context_retrieval_results || {};
  const map = {
    astrophysical_interpreter: Number(astro.confidence ?? 0.55),
    artefact_checker: Number(art.artefact_probability ?? 0.45),
    novelty_assessor: Number(nov.overall_interest_score ?? 0.5),
    context_retriever: Math.min(1, ((ctx.raw_arxiv_papers || []).length || 1) / 4),
    evidence_aggregator: Number(agg.overall_interest_score ?? 0.65),
    followup_prioritizer: ((st.followup_recommendations?.priority_actions || []).length || 1) / 5,
    code_executor: st.code_execution_output?.skipped ? 0.15 : 0.55,
    synthesis: 0.4,
    observation_characterizer: 0.7,
    supervisor: st.needs_code ? 0.55 : 0.35,
  };
  return Math.max(0, Math.min(1, map[agentId] ?? 0.3));
}

function renderScience() {
  drawRadar();
  const agg = state.current?.state?.aggregated_evidence || {};
  const hypotheses = agg.ranked_hypotheses || [];
  $("hypothesesList").innerHTML = hypotheses.length
    ? hypotheses.map((h) => `
      <div class="hypothesis">
        <strong>${escapeHtml(h.hypothesis)}</strong>
        <div class="confidence-bar"><div class="confidence-fill" style="width:${scorePercent(h.updated_confidence)}%"></div></div>
        <p class="muted">Confidence ${fmtNum(Number(h.updated_confidence))}. Key discriminant: ${escapeHtml(h.key_discriminant || "not stated")}</p>
      </div>
    `).join("")
    : `<p class="muted">Run a packet from the dashboard to persist complete hypotheses.</p>`;

  $("debateList").innerHTML = [
    ["Agreement", agg.agreement_points || []],
    ["Disagreement", agg.disagreement_points || []],
    ["Unresolved", agg.unresolved_questions || []],
  ].map(([title, items]) => `
    <div class="debate-card">
      <strong>${title}</strong>
      ${items.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : `<p class="muted">No structured entries available.</p>`}
    </div>
  `).join("");
}

function renderPerformance() {
  const timings = (state.current?.timing_log || []).filter((item) => !item.node?.startsWith("_"));
  const max = Math.max(...timings.map((item) => item.duration_ms || 0), 1);
  $("timeline").innerHTML = timings.map((item) => `
    <div class="timeline-row">
      <strong>${escapeHtml(item.node)}</strong>
      <div class="timeline-track"><div class="timeline-fill" style="width:${Math.max(2, (item.duration_ms || 0) / max * 100)}%"></div></div>
      <span>${fmtMs(item.duration_ms)}</span>
    </div>
  `).join("") || `<p class="muted">No timing entries available.</p>`;
  drawTokenChart();

  const agents = state.current?.agents || [];
  $("influenceMap").innerHTML = agents
    .filter((agent) => !["supervisor", "synthesis"].includes(agent.id))
    .map((agent) => {
      const influence = getInfluence(agent.id);
      return `
        <div class="influence-row">
          <strong>${escapeHtml(agent.label)}</strong>
          <div class="influence-track"><div class="influence-fill" style="width:${scorePercent(influence)}%"></div></div>
          <p class="muted">${fmtNum(influence)} downstream influence estimate</p>
        </div>
      `;
    }).join("");
}

function renderData() {
  drawLightcurve();
  const probs = state.current?.data_products?.probabilities || [];
  $("probabilityBars").innerHTML = probs.length
    ? probs.slice(0, 10).map((item) => `
      <div class="prob-row">
        <strong>${escapeHtml(item.class_name || item.classifier_name)}</strong>
        <div class="probability-track"><div class="probability-fill" style="width:${scorePercent(item.probability)}%"></div></div>
        <span>${fmtNum(Number(item.probability))}</span>
      </div>
    `).join("")
    : `<p class="muted">No probability file found for this packet.</p>`;
  $("packetMetadata").textContent = JSON.stringify(state.current?.packet?.metadata || state.current?.packet || {}, null, 2);
}

function renderReport() {
  const report = state.current?.state?.synthesis_report || "No full synthesis report is stored for this run. Use the dashboard run button to execute a packet and persist the final state.";
  $("reportContent").innerHTML = markdownLite(report);
}

function markdownLite(md) {
  const lines = escapeHtml(md).split("\n");
  let html = "";
  let inList = false;
  let inPre = false;
  for (const line of lines) {
    if (line.startsWith("```")) {
      html += inPre ? "</pre>" : "<pre>";
      inPre = !inPre;
      continue;
    }
    if (inPre) {
      html += `${line}\n`;
      continue;
    }
    if (line.startsWith("### ")) {
      if (inList) html += "</ol>";
      inList = false;
      html += `<h3>${line.slice(4)}</h3>`;
    } else if (line.startsWith("## ")) {
      if (inList) html += "</ol>";
      inList = false;
      html += `<h2>${line.slice(3)}</h2>`;
    } else if (/^\d+\.\s/.test(line)) {
      if (!inList) html += "<ol>";
      inList = true;
      html += `<li>${line.replace(/^\d+\.\s/, "")}</li>`;
    } else if (line.trim()) {
      if (inList) html += "</ol>";
      inList = false;
      html += `<p>${line.replaceAll("**", "")}</p>`;
    }
  }
  if (inList) html += "</ol>";
  return html;
}

function drawSky() {
  const canvas = $("skyCanvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const grad = ctx.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0, "#0e1820");
  grad.addColorStop(0.55, "#18303a");
  grad.addColorStop(1, "#421f1a");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
  const stars = [
    [64, 54, 1.2], [140, 132, 1.7], [250, 82, 1.1], [344, 176, 2],
    [470, 48, 1.4], [585, 118, 1.1], [668, 70, 1.8], [520, 230, 1.5],
    [212, 235, 1.2], [90, 220, 1.6], [630, 260, 1.1],
  ];
  ctx.strokeStyle = "rgba(188, 218, 220, 0.38)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  [stars[1], stars[3], stars[5], stars[7], stars[8], stars[1]].forEach(([x, y], idx) => {
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  stars.forEach(([x, y, r]) => {
    ctx.beginPath();
    ctx.fillStyle = "rgba(244, 249, 250, 0.92)";
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.beginPath();
  ctx.strokeStyle = "rgba(199, 71, 50, 0.75)";
  ctx.lineWidth = 2.5;
  ctx.ellipse(530, 160, 110, 32, -0.25, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.fillStyle = "rgba(23, 108, 114, 0.48)";
  ctx.arc(530, 160, 46, 0, Math.PI * 2);
  ctx.fill();
}

function drawRadar() {
  const canvas = $("radarCanvas");
  const ctx = canvas.getContext("2d");
  const novel = state.current?.state?.novelty_rarity_assessment || {};
  const values = [
    ["Rarity", novel.rarity_score],
    ["Novelty", novel.novelty_score],
    ["Uncertainty", novel.uncertainty_score],
    ["Follow-up", novel.followup_value_score],
    ["Interest", novel.overall_interest_score],
  ].map(([label, value]) => [label, Number(value ?? 0)]);
  drawPolygonChart(ctx, canvas.width, canvas.height, values);
}

function drawPolygonChart(ctx, w, h, values) {
  ctx.clearRect(0, 0, w, h);
  const cx = w / 2;
  const cy = h / 2 + 8;
  const radius = Math.min(w, h) * 0.34;
  ctx.strokeStyle = "#d9dee5";
  ctx.fillStyle = "#66717e";
  ctx.font = "12px system-ui";
  for (let ring = 1; ring <= 4; ring++) {
    ctx.beginPath();
    values.forEach((_, i) => {
      const a = -Math.PI / 2 + (Math.PI * 2 * i) / values.length;
      const r = radius * ring / 4;
      const x = cx + Math.cos(a) * r;
      const y = cy + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
  }
  ctx.beginPath();
  values.forEach(([label, value], i) => {
    const a = -Math.PI / 2 + (Math.PI * 2 * i) / values.length;
    const x = cx + Math.cos(a) * radius * value;
    const y = cy + Math.sin(a) * radius * value;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
    ctx.fillText(label, cx + Math.cos(a) * (radius + 28) - 28, cy + Math.sin(a) * (radius + 24));
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(23, 108, 114, 0.22)";
  ctx.strokeStyle = "#176c72";
  ctx.lineWidth = 2;
  ctx.fill();
  ctx.stroke();
}

function drawTokenChart() {
  const canvas = $("tokenCanvas");
  const ctx = canvas.getContext("2d");
  const tokens = state.current?.token_counts || [];
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const max = Math.max(...tokens.map((t) => t.total_tokens || 0), 1);
  const barH = 18;
  ctx.font = "12px system-ui";
  tokens.slice(0, 9).forEach((t, i) => {
    const y = 24 + i * 31;
    ctx.fillStyle = "#66717e";
    ctx.fillText(t.node, 12, y + 13);
    ctx.fillStyle = "#176c72";
    ctx.fillRect(178, y, (t.input_tokens || 0) / max * 250, barH);
    ctx.fillStyle = "#c74732";
    ctx.fillRect(178 + (t.input_tokens || 0) / max * 250, y, (t.output_tokens || 0) / max * 250, barH);
    ctx.fillStyle = "#17202a";
    ctx.fillText(String(t.total_tokens || 0), 445, y + 13);
  });
}

function drawLightcurve() {
  const canvas = $("lightcurveCanvas");
  const ctx = canvas.getContext("2d");
  const rows = state.current?.data_products?.lightcurve || [];
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#66717e";
  ctx.font = "14px system-ui";
  if (!rows.length) {
    ctx.fillText("No light-curve CSV found for this packet.", 24, 42);
    return;
  }
  const points = rows
    .filter((r) => Number.isFinite(r.mjd) && Number.isFinite(r.magpsf))
    .map((r) => ({ x: r.mjd, y: r.magpsf, fid: r.fid }));
  const minX = Math.min(...points.map((p) => p.x));
  const maxX = Math.max(...points.map((p) => p.x));
  const minY = Math.min(...points.map((p) => p.y));
  const maxY = Math.max(...points.map((p) => p.y));
  const pad = 42;
  ctx.strokeStyle = "#d9dee5";
  ctx.strokeRect(pad, pad, canvas.width - pad * 1.5, canvas.height - pad * 1.7);
  ctx.fillText("MJD", canvas.width / 2, canvas.height - 12);
  ctx.save();
  ctx.translate(14, canvas.height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("magpsf (brighter is higher)", 0, 0);
  ctx.restore();
  const scaleX = (x) => pad + ((x - minX) / Math.max(1, maxX - minX)) * (canvas.width - pad * 2);
  const scaleY = (y) => pad + ((y - minY) / Math.max(0.1, maxY - minY)) * (canvas.height - pad * 2.2);
  const byFilter = new Map();
  points.forEach((p) => {
    const key = String(p.fid || "unknown");
    if (!byFilter.has(key)) byFilter.set(key, []);
    byFilter.get(key).push(p);
  });
  const colors = ["#176c72", "#c74732", "#805b10"];
  Array.from(byFilter.values()).forEach((series, idx) => {
    series.sort((a, b) => a.x - b.x);
    ctx.strokeStyle = colors[idx % colors.length];
    ctx.fillStyle = colors[idx % colors.length];
    ctx.beginPath();
    series.forEach((p, i) => {
      const x = scaleX(p.x);
      const y = scaleY(p.y);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    series.forEach((p) => {
      ctx.beginPath();
      ctx.arc(scaleX(p.x), scaleY(p.y), 3, 0, Math.PI * 2);
      ctx.fill();
    });
  });
}

init().catch((err) => {
  $("objectTitle").textContent = "Dashboard failed to load";
  $("summaryLabel").textContent = err.message;
  console.error(err);
});
