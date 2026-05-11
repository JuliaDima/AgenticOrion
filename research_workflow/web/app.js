const state = {
  workflow: null,
  packets: [],
  runs: [],
  benchmark: null,
  current: null,
  selectedAgent: null,
  staticMode: false,
  activeTab: "project",
};

const $ = (id) => document.getElementById(id);
const STATIC_DATA_ROOT = "static-data";
const PROJECT_NODE_DETAILS = {
  packet: {
    title: "Observation Packet",
    group: "input",
    purpose: "A compact, curated astronomy packet containing object identifiers, mission context, modalities, metadata, local data products, and archive query hints.",
    reads: "packet.json, manifest metadata, CSV/JSON/FITS data products when available",
    writes: "Initial ResearchState",
    influences: "Defines every downstream prompt and which evidence streams are available.",
  },
  supervisor: {
    title: "Supervisor",
    group: "routing",
    purpose: "Confirms mission and primary modality, then decides whether lightweight code analysis could improve the triage.",
    reads: "mission, modalities, labels, packet summary, data availability",
    writes: "mission, primary_modality, needs_code",
    influences: "Controls whether code_executor is reachable later in the graph.",
  },
  observation_characterizer: {
    title: "Observation Characterizer",
    group: "preamble",
    purpose: "Summarizes the observation, extracts salient features, and lists missing evidence, uncertainties, and data-quality notes.",
    reads: "full packet plus local packet data summaries",
    writes: "observation_characterization",
    influences: "Provides the shared context used by all four parallel branches.",
  },
  astrophysical_interpreter: {
    title: "Astrophysical Interpreter",
    group: "parallel branch",
    purpose: "Tests known astrophysical explanations and assigns evidence-backed plausibility to candidate classes.",
    reads: "packet metadata and characterization",
    writes: "candidate classes, best explanation, astrophysical confidence",
    influences: "Raises or lowers confidence in real astrophysical hypotheses.",
  },
  artefact_checker: {
    title: "Artefact Checker",
    group: "parallel branch",
    purpose: "Assesses whether detector, telescope, calibration, image-subtraction, or pipeline effects could explain the signal.",
    reads: "modality, labels, data-quality notes, salient features",
    writes: "artefact modes, artefact probability, recommended quality checks",
    influences: "Can penalize astrophysical confidence and redirect follow-up toward validation checks.",
  },
  novelty_assessor: {
    title: "Novelty Assessor",
    group: "parallel branch",
    purpose: "Scores rarity, novelty, uncertainty, follow-up value, and time sensitivity.",
    reads: "packet summary, labels, missing evidence, uncertainties",
    writes: "novelty/rareness/follow-up scores and scientific-interest rationale",
    influences: "Contributes the attention-allocation score used by aggregation.",
  },
  context_retriever: {
    title: "Context Retriever",
    group: "parallel branch",
    purpose: "Retrieves and summarizes literature, catalogue context, historical analogues, and mission-specific failure modes.",
    reads: "mission, object class, packet labels, arXiv query hints",
    writes: "related papers, context summaries, known failure modes",
    influences: "Grounds branch debate in external scientific context.",
  },
  evidence_aggregator: {
    title: "Evidence Aggregator",
    group: "debate",
    purpose: "Performs the fan-in debate: compares branch outputs, ranks hypotheses, surfaces agreement/disagreement, and sets the triage verdict.",
    reads: "all four parallel branch outputs and parallel timing",
    writes: "ranked hypotheses, confidence updates, interest score, verdict",
    influences: "Determines the scientific priority and whether code analysis remains useful.",
  },
  followup_prioritizer: {
    title: "Follow-up Prioritizer",
    group: "action",
    purpose: "Ranks follow-up actions by discriminating power, urgency, feasibility, and scientific value.",
    reads: "triage verdict, ranked hypotheses, unresolved questions",
    writes: "priority actions, facilities, time-sensitivity note",
    influences: "Turns the triage result into an observing/checking plan.",
  },
  code_executor: {
    title: "Code Executor",
    group: "optional analysis",
    purpose: "When requested, generates and runs lightweight Python metrics over local data products.",
    reads: "available local files, top hypotheses, unresolved questions",
    writes: "code, stdout/stderr, quantitative metrics",
    influences: "Adds measurable evidence such as rise rates, amplitudes, or catalogue summaries.",
  },
  synthesis: {
    title: "Synthesis",
    group: "report",
    purpose: "Produces the final traceable Markdown report for scientific review.",
    reads: "all agent outputs, timing, tools, code output, and references",
    writes: "synthesis_report",
    influences: "Packages the run into a readable, auditable scientific summary.",
  },
};

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

function fmtPct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "--";
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
  if (url === "/api/benchmark") return `${STATIC_DATA_ROOT}/benchmark.json`;
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
  bindHeroPhotos();
  state.workflow = await fetchJson("/api/workflow");
  state.packets = await fetchJson("/api/packets");
  state.benchmark = await fetchJson("/api/benchmark").catch(() => null);
  populatePackets();
  renderProject();
  await refreshRuns();
  bindEvents();
  const requestedTab = normalizeRoute(window.location.hash?.replace("#", ""));
  if (requestedTab === "project") {
    showHome(false);
  } else {
    await activateTab(requestedTab, false);
  }
}

function bindHeroPhotos() {
  [
    ["overviewHeroImage", ".sky-panel"],
  ].forEach(([imageId, panelSelector]) => {
    const img = $(imageId);
    const panel = img?.closest(panelSelector);
    if (!img || !panel) return;
    const markLoaded = () => {
      if (img.naturalWidth > 0) panel.classList.add("has-photo");
    };
    img.addEventListener("load", markLoaded);
    img.addEventListener("error", () => panel.classList.remove("has-photo"));
    if (img.complete) markLoaded();
  });
}

function bindEvents() {
  $("homeButton").addEventListener("click", () => showHome(true));
  $("runButton")?.addEventListener("click", runSelectedPacket);
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });
  window.addEventListener("hashchange", () => {
    const tab = normalizeRoute(window.location.hash.replace("#", ""));
    if (tab === "project") {
      showHome(false);
    } else if (document.getElementById(tab)) {
      activateTab(tab, false);
    }
  });
}

async function activateTab(tabName, updateHash = true) {
  tabName = normalizeRoute(tabName);
  if (tabName === "project" || !state.current) {
    showHome(updateHash);
    return;
  }
  state.activeTab = tabName;
  setPageMode("object");
  setObjectTabsVisible(true);
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabName));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === tabName));
  if (updateHash) history.replaceState(null, "", `#${tabName}`);
}

function normalizeRoute(route) {
  if (!route || route === "home" || route === "project") return "project";
  return route;
}

function showHome(updateHash = true) {
  state.current = null;
  state.selectedAgent = null;
  state.activeTab = "project";
  setPageMode("home");
  setObjectTabsVisible(false);
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === "project"));
  if (updateHash) history.replaceState(null, "", "#home");
  renderProjectLandingHeader();
  renderProject();
  renderWorkflow();
  renderInspector(null);
  renderRunList();
}

function setObjectTabsVisible(visible) {
  const tabs = $("objectTabs");
  if (tabs) tabs.hidden = !visible;
}

function setPageMode(mode) {
  document.body.classList.toggle("home-mode", mode === "home");
  document.body.classList.toggle("object-mode", mode === "object");
}

function populatePackets() {
  if (!$("packetSelect")) return;
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
      const blindBadge = run.experiment_type === "BLIND" ? `<span class="blind-badge">BLIND</span>` : "";
      return `
        <button class="run-item${active}" data-run="${escapeHtml(run.run_id)}">
          <strong>${blindBadge}${escapeHtml(run.object_id || run.query || "Run")}</strong>
          <span>${escapeHtml(run.status)} | ${fmtMs(run.duration_ms)} | ${escapeHtml(score)}${tokens}</span>
        </button>
      `;
    })
    .join("");
  document.querySelectorAll(".run-item").forEach((item) => {
    item.addEventListener("click", () => loadRun(item.dataset.run));
  });
}

async function loadRun(runId, switchToWorkflow = true) {
  state.current = await fetchJson(`/api/runs/${runId}`);
  state.selectedAgent = state.current.agents.find((agent) => agent.id === "evidence_aggregator") || state.current.agents[0];
  if (switchToWorkflow) activateTab("workflow");
  renderAll();
}

async function runSelectedPacket() {
  if (state.staticMode || window.location.hostname.endsWith("github.io")) {
    if ($("runStatus")) $("runStatus").textContent = "GitHub Pages is static. Run packets from the local dashboard.";
    return;
  }
  const packetIndex = Number($("packetSelect")?.value || 1);
  if ($("runButton")) $("runButton").disabled = true;
  if ($("runStatus")) $("runStatus").textContent = "Running workflow. This can take about a minute.";
  try {
    state.current = await fetchJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ packet_index: packetIndex }),
    });
    await refreshRuns();
    state.selectedAgent = state.current.agents.find((agent) => agent.id === "evidence_aggregator") || state.current.agents[0];
    activateTab("workflow");
    renderAll();
    if ($("runStatus")) $("runStatus").textContent = "Run complete.";
  } catch (err) {
    if ($("runStatus")) $("runStatus").textContent = err.message;
  } finally {
    if ($("runButton")) $("runButton").disabled = false;
  }
}

function renderAll() {
  renderRunList();
  renderHeader();
  renderProject();
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

  setMetricLabels([
    ["Interest", "scientific attention score"],
    ["Wall time", "end-to-end execution"],
    ["Parallel speedup", "fan-out efficiency"],
    ["Consumption", "tokens and estimated cost"],
  ]);
  const isBlind = (packet.experiment_type || run.experiment_type) === "BLIND";
  $("objectTitle").innerHTML = isBlind
    ? `<span class="blind-badge blind-badge-lg">BLIND</span> ${escapeHtml(run.object_id || "Observation")}`
    : escapeHtml(`${run.object_id || "Observation"} | ${packet.experiment_type || "workflow run"}`);
  $("statusPill").textContent = run.status || "idle";
  $("missionLabel").textContent = isBlind
    ? `${packet.mission || run.query || "Mission"} — anonymised run`
    : (packet.mission || run.query || "Mission");
  $("verdictLabel").textContent = verdict;
  $("summaryLabel").textContent = packet.short_summary || metrics.metric_note || "Existing database trace without full final state. Run a packet from the dashboard to persist complete structured outputs.";
  renderHeroFacts(packet, run, agg, novel, metrics);
  document.querySelector(".sky-panel")?.classList.remove("has-photo");
  drawObjectHero();
  $("interestMetric").textContent = interest !== null && interest !== undefined ? fmtNum(Number(interest)) : "--";
  $("wallMetric").textContent = fmtMs(metrics.total_wall_ms || run.duration_ms);
  $("speedMetric").textContent = metrics.speedup ? `${fmtNum(metrics.speedup)}x` : "--";
  $("tokenMetric").textContent = metrics.total_tokens !== null && metrics.total_tokens !== undefined
    ? `${metrics.total_tokens.toLocaleString()} tok · ${fmtCost(metrics.estimated_cost_usd)}`
    : (run.status === "running" ? "pending" : (metrics.consumption_note ? "not logged" : "--"));
}

function renderProjectLandingHeader() {
  const packets = state.packets || [];
  const runs = state.runs || [];
  const missions = new Set(packets.map((p) => p.mission).filter(Boolean));
  const completed = runs.filter((r) => r.status === "success").length;
  const totalTokens = runs.reduce((sum, r) => sum + (Number(r.total_tokens) || 0), 0);
  setMetricLabels([
    ["Objects", "curated observation packets"],
    ["Missions", "survey/instrument families"],
    ["Completed", "successful logged runs"],
    ["Tokens", "logged model consumption"],
  ]);
  $("objectTitle").textContent = "Agentic Orion";
  $("statusPill").textContent = "overview";
  $("missionLabel").textContent = "";
  $("verdictLabel").textContent = "Multi-agent attention allocation for next-generation deep-space discovery";
  $("summaryLabel").textContent = "Agentic Orion receives compact observation packets, decomposes each scientific question across specialized LangGraph agents, and returns a traceable triage report for human inspection.";
  $("heroFacts").innerHTML = [
    `${packets.length} curated objects`,
    `${missions.size} mission streams`,
    `${runs.length} archived runs`,
    `${completed} completed analyses`,
    totalTokens ? `${totalTokens.toLocaleString()} logged model tokens` : "model tokens pending",
  ].map((fact) => `<span>${escapeHtml(fact)}</span>`).join("");
  $("interestMetric").textContent = String(packets.length || "--");
  $("wallMetric").textContent = String(missions.size || "--");
  $("speedMetric").textContent = String(completed || "--");
  $("tokenMetric").textContent = totalTokens ? `${totalTokens.toLocaleString()} tok` : "pending";
  const overviewImg = $("overviewHeroImage");
  if (overviewImg?.naturalWidth > 0) {
    document.querySelector(".sky-panel")?.classList.add("has-photo");
  }
  const canvas = $("skyCanvas");
  drawProjectMissionHero(canvas.getContext("2d"), canvas.width, canvas.height);
}

function setMetricLabels(labels) {
  document.querySelectorAll(".metric-card").forEach((card, index) => {
    const label = labels[index];
    if (!label) return;
    const span = card.querySelector("span");
    const small = card.querySelector("small");
    if (span) span.textContent = label[0];
    if (small) small.textContent = label[1];
  });
}

function renderHeroFacts(packet, run, agg, novel, metrics) {
  const ids = packet.object_or_event_id || {};
  const labels = packet.initial_pipeline_labels || [];
  const facts = [
    ids.redshift !== undefined ? `z ${ids.redshift}` : null,
    ids.host_redshift !== undefined ? `host z ${ids.host_redshift}` : null,
    ids.lens_z !== undefined && ids.source_z !== undefined ? `lens z ${ids.lens_z} / source z ${ids.source_z}` : null,
    ids.DM_pc_cm3 !== undefined ? `DM ${ids.DM_pc_cm3} pc cm-3` : null,
    packet.modality?.length ? packet.modality.join(" + ") : null,
    labels[0],
    agg.ranked_hypotheses?.[0]?.hypothesis || run.triage_verdict,
    metrics.total_tokens ? `${Number(metrics.total_tokens).toLocaleString()} tokens` : null,
    novel.time_sensitive ? "time-sensitive" : null,
  ].filter(Boolean).slice(0, 5);
  $("heroFacts").innerHTML = facts.map((fact) => `<span>${escapeHtml(fact)}</span>`).join("");
}

const graphPositions = {
  START: [324, 20],
  supervisor: [324, 100],
  observation_characterizer: [324, 180],
  astrophysical_interpreter: [84, 290],
  artefact_checker: [244, 290],
  novelty_assessor: [404, 290],
  context_retriever: [564, 290],
  evidence_aggregator: [324, 410],
  followup_prioritizer: [220, 488],
  code_executor: [428, 554],
  synthesis: [324, 648],
};

function renderWorkflow() {
  const svg = $("agentGraph");
  svg.setAttribute("viewBox", "0 0 760 760");
  const agents = state.current?.agents || state.workflow?.agents || [];
  const byId = Object.fromEntries(agents.map((a) => [a.id, a]));

  const NW = 112, NH = 48;
  const botC = (id) => { const [x, y] = graphPositions[id] || [0, 0]; return [x + NW / 2, y + NH]; };
  const topC = (id) => { const [x, y] = graphPositions[id] || [0, 0]; return [x + NW / 2, y]; };

  const FANOUT_FROM = new Set(["observation_characterizer"]);
  const FANOUT_TO   = new Set(["astrophysical_interpreter", "artefact_checker", "novelty_assessor", "context_retriever"]);

  const GROUP_COLOR = {
    start: "#94a3b8", input: "#94a3b8", routing: "#7c3aed", preamble: "#0d9488",
    "parallel branch": "#3b82f6", debate: "#f59e0b",
    action: "#0d9488", "optional analysis": "#d97706", report: "#64748b",
  };

  const workflowEdges = (state.workflow?.edges || []).filter(([f, t]) => graphPositions[f] && graphPositions[t]);

  let edgeSvg = "";

  for (const [from, to] of workflowEdges) {
    const [bx, by] = botC(from);
    const [tx, ty] = topC(to);
    const isFanout = FANOUT_FROM.has(from) && FANOUT_TO.has(to);
    const isFanin  = FANOUT_TO.has(from);
    const cls = isFanout ? "g-edge g-edge-fanout" : isFanin ? "g-edge g-edge-fanin" : "g-edge";
    const mid = (isFanout || isFanin) ? "arrow-teal" : "arrow-slate";
    const dy = ty - by;
    let pathD;
    if (dy < 0 && Math.abs(tx - bx) > 80) {
      pathD = `M ${bx} ${by} C ${bx} ${by + 44}, ${tx} ${ty + 44}, ${tx} ${ty}`;
    } else {
      const cp = Math.max(36, Math.abs(dy) * 0.44);
      pathD = `M ${bx} ${by} C ${bx} ${by + cp}, ${tx} ${ty - cp}, ${tx} ${ty}`;
    }
    edgeSvg += `<path class="${cls}" marker-end="url(#${mid})" d="${pathD}" />`;
  }

  // Needs-code edge: supervisor → code_executor (purple dashed, right-side sweep)
  {
    const [sx, sy] = graphPositions["supervisor"] || [291, 125];
    const [tx, ty] = topC("code_executor");
    const rx = sx + NW, ry = sy + NH / 2;
    edgeSvg += `<path class="g-edge g-edge-code" marker-end="url(#arrow-purple)" d="M ${rx} ${ry} C ${rx + 110} ${ry}, ${tx + 88} ${ty - 56}, ${tx} ${ty}" />`;
    edgeSvg += `<text class="g-edge-label g-edge-label-code" x="${rx + 8}" y="${ry - 9}">needs_code</text>`;
  }

  const nodes = [{ id: "START", label: "START", group: "start" }, ...agents];
  const nodeMarkup = nodes.filter((n) => graphPositions[n.id]).map((node) => {
    const [x, y] = graphPositions[node.id];
    const active = state.selectedAgent?.id === node.id ? " active" : "";
    const timing = node.id === "START" ? "" : fmtMs(byId[node.id]?.timing?.duration_ms || byId[node.id]?.call?.duration_ms);
    const sub = node.id === "START" ? "input packet" : (node.group || "");
    const accent = GROUP_COLOR[node.group] || "#0d9488";
    return `
      <g class="node-card${active}" data-agent="${escapeHtml(node.id)}" transform="translate(${x}, ${y})">
        <rect class="nc-bg" width="${NW}" height="${NH}" rx="8" />
        <rect class="nc-accent" x="0" y="5" width="3" height="${NH - 10}" rx="1.5" fill="${accent}" />
        <text class="node-title" x="11" y="19" font-size="11.5">${escapeHtml(node.label || node.id)}</text>
        <text class="node-sub" x="11" y="31" font-size="9">${escapeHtml(sub)}</text>
        ${timing ? `<text class="node-time" x="11" y="43" font-size="9">${escapeHtml(timing)}</text>` : ""}
      </g>`;
  }).join("");

  svg.innerHTML = `
    <defs>
      <filter id="nc-shadow" x="-15%" y="-15%" width="130%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#0f172a" flood-opacity="0.10" />
      </filter>
      <marker id="arrow-slate"  markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#94a3b8" /></marker>
      <marker id="arrow-teal"   markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#0d9488" /></marker>
      <marker id="arrow-purple" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#7c3aed" /></marker>
      <marker id="arrow-amber"  markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#f59e0b" /></marker>
    </defs>
    ${edgeSvg}
    ${nodeMarkup}`;

  svg.querySelectorAll(".node-card").forEach((node) => {
    node.addEventListener("click", () => {
      const agent = state.current?.agents?.find((a) => a.id === node.dataset.agent)
        || state.workflow?.agents?.find((a) => a.id === node.dataset.agent);
      if (agent) { state.selectedAgent = agent; renderWorkflow(); renderInspector(agent); }
    });
  });
}

function renderInspector(agent) {
  if (!agent) {
    $("agentInspector").innerHTML = `
      <p class="eyebrow">General workflow</p>
      <h3>LangGraph architecture</h3>
      <p class="muted">This view shows the static graph design. Select a node to read its role, or select a run from the sidebar to inspect object-specific reasoning traces, timings, tools, and token use.</p>
      <div class="inspector-section">
        <h4>Execution Shape</h4>
        ${kv("Preamble", "Supervisor then observation characterizer")}
        ${kv("Parallel fan-out", "Astrophysical, artefact, novelty, and context agents")}
        ${kv("Fan-in", "Evidence aggregator debates branch outputs")}
        ${kv("Output", "Follow-up plan, optional code execution, synthesis report")}
      </div>
    `;
    return;
  }
  const call = agent.call || {};
  const tokens = agent.tokens || {};
  const timing = agent.timing || {};
  const outputs = agent.outputs || {};
  const influence = getInfluence(agent.id);
  const hasRunTrace = Boolean(state.current && call.agent_name);
  $("agentInspector").innerHTML = `
    <p class="eyebrow">${escapeHtml(agent.group || "agent")}</p>
    <h3>${escapeHtml(agent.label || agent.id)}</h3>
    <p class="muted">${escapeHtml(agent.role || "")}</p>
    <div class="inspector-section">
      <h4>${hasRunTrace ? "Trace" : "General Role"}</h4>
      ${hasRunTrace ? `
        ${kv("Started", shortTime(call.start_time || timing.timestamp))}
        ${kv("Duration", fmtMs(call.duration_ms || timing.duration_ms))}
        ${kv("Status", call.error ? "error" : "ok")}
        ${kv("Input", call.input_summary || "No call summary available")}
        ${kv("Output", call.output_summary || "No output summary available")}
      ` : `
        ${kv("Purpose", agent.role || "Workflow node")}
        ${kv("Group", agent.group || "agent")}
        ${kv("Trace data", "Select a run to inspect live outputs")}
      `}
    </div>
    <div class="inspector-section">
      <h4>Consumption</h4>
      ${hasRunTrace ? `
        ${kv("Input tokens", tokens.input_tokens?.toLocaleString?.() || "0")}
        ${kv("Output tokens", tokens.output_tokens?.toLocaleString?.() || "0")}
        ${kv("Total tokens", tokens.total_tokens?.toLocaleString?.() || "0")}
        ${kv("Influence", `${fmtNum(influence)} / 1.00`)}
      ` : `<p class="muted">Token and influence metrics are run-specific and hidden in the general graph.</p>`}
    </div>
    <div class="inspector-section" ${hasRunTrace ? "" : "hidden"}>
      <h4>Structured Output</h4>
      ${renderStructuredOutput(agent.id, outputs)}
    </div>
    <div class="inspector-section" ${hasRunTrace ? "" : "hidden"}>
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

function renderStructuredOutput(agentId, outputs) {
  if (!outputs || !Object.keys(outputs).length) return `<p class="muted">No structured output recorded.</p>`;

  const scoreBar = (v) => {
    const pct = Math.round(Math.max(0, Math.min(1, Number(v) || 0)) * 100);
    return `<div class="so-score-row"><div class="so-score-track"><div class="so-score-fill" style="width:${pct}%"></div></div><span class="so-score-label">${fmtNum(Number(v))}</span></div>`;
  };

  const evidenceList = (items, type) => {
    if (!items?.length) return "";
    return `<ul class="so-evidence-list so-evidence-${type}">${items.map(e => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`;
  };

  const chip = (text, cls) => `<span class="so-chip so-chip-${cls}">${escapeHtml(text)}</span>`;

  // ── Astrophysical Interpreter ───────────────────────────────────────────────
  if (agentId === "astrophysical_interpreter") {
    const d = outputs.astrophysical_interpretation || {};
    const classes = d.candidate_classes || [];
    return `
      <div class="so-lead">
        <div class="so-lead-label">Best explanation</div>
        <div class="so-lead-value">${escapeHtml(d.best_explanation || "—")}</div>
        ${scoreBar(d.confidence)}
        ${d.uncertainty_notes ? `<p class="so-note">${escapeHtml(d.uncertainty_notes)}</p>` : ""}
      </div>
      ${classes.map(c => `
        <div class="so-candidate">
          <div class="so-candidate-header">
            <strong>${escapeHtml(c.name)}</strong>
            ${scoreBar(c.probability)}
          </div>
          ${evidenceList(c.evidence_for, "for")}
          ${evidenceList(c.evidence_against, "against")}
        </div>
      `).join("")}
    `;
  }

  // ── Artefact Checker ────────────────────────────────────────────────────────
  if (agentId === "artefact_checker") {
    const d = outputs.artefact_assessment || {};
    const modes = d.possible_artefact_modes || [];
    return `
      <div class="so-lead">
        <div class="so-lead-label">Artefact probability</div>
        ${scoreBar(d.artefact_probability)}
        <div class="so-lead-value">${escapeHtml(d.most_likely_non_astrophysical || "—")}</div>
      </div>
      ${modes.map(m => `
        <div class="so-candidate">
          <div class="so-candidate-header">
            <strong>${escapeHtml(m.name)}</strong>
            ${scoreBar(m.probability)}
          </div>
          ${evidenceList(m.evidence_for, "for")}
          ${evidenceList(m.evidence_against, "against")}
        </div>
      `).join("")}
      ${(d.recommended_quality_checks || []).length ? `
        <div class="so-section-label">Recommended checks</div>
        <ul class="so-checks-list">${(d.recommended_quality_checks || []).map(c => `<li>${escapeHtml(c)}</li>`).join("")}</ul>
      ` : ""}
    `;
  }

  // ── Novelty Assessor ────────────────────────────────────────────────────────
  if (agentId === "novelty_assessor") {
    const d = outputs.novelty_rarity_assessment || {};
    return `
      ${d.time_sensitive ? `<div class="so-alert">⚡ Time-sensitive observation</div>` : ""}
      <div class="so-scores-grid">
        ${[["Rarity", d.rarity_score], ["Novelty", d.novelty_score], ["Uncertainty", d.uncertainty_score], ["Follow-up value", d.followup_value_score], ["Overall interest", d.overall_interest_score]].map(([label, val]) => `
          <div class="so-score-card">
            <div class="so-section-label">${label}</div>
            ${scoreBar(val)}
          </div>
        `).join("")}
      </div>
      ${d.reason_for_scientific_interest ? `<p class="so-reason">${escapeHtml(d.reason_for_scientific_interest)}</p>` : ""}
      ${d.ood_notes ? `<p class="so-note">${escapeHtml(d.ood_notes)}</p>` : ""}
    `;
  }

  // ── Context Retriever ───────────────────────────────────────────────────────
  if (agentId === "context_retriever") {
    const d = outputs.context_retrieval_results || {};
    const papers = d.related_papers || [];
    const arxiv = d.raw_arxiv_papers || [];
    return `
      ${papers.map(p => `
        <div class="so-paper">
          <div class="so-paper-title">${escapeHtml(p.title || "Untitled")}</div>
          ${p.key_finding ? `<p class="so-paper-finding">${escapeHtml(p.key_finding)}</p>` : ""}
          ${p.relevance ? `<p class="so-note">${escapeHtml(p.relevance)}</p>` : ""}
        </div>
      `).join("")}
      ${arxiv.length ? `
        <div class="so-section-label" style="margin-top:12px">arXiv references</div>
        ${arxiv.slice(0, 5).map(p => `
          <div class="so-paper so-paper-arxiv">
            <a class="so-paper-title so-paper-link" href="${escapeHtml(p.url || "#")}" target="_blank" rel="noopener">${escapeHtml(p.title || "Untitled")}</a>
            <p class="so-note">${escapeHtml(p.abstract?.slice(0, 180) || "")}…</p>
          </div>
        `).join("")}
      ` : ""}
      ${d.relevant_catalogue_context ? `<p class="so-note"><strong>Catalogue:</strong> ${escapeHtml(d.relevant_catalogue_context)}</p>` : ""}
      ${d.mission_instrument_notes ? `<p class="so-note"><strong>Mission notes:</strong> ${escapeHtml(d.mission_instrument_notes)}</p>` : ""}
      ${(d.known_failure_modes || []).length ? `
        <div class="so-section-label">Known failure modes</div>
        <ul class="so-evidence-list so-evidence-against">${(d.known_failure_modes || []).map(f => `<li>${escapeHtml(f)}</li>`).join("")}</ul>
      ` : ""}
    `;
  }

  // ── Evidence Aggregator ─────────────────────────────────────────────────────
  if (agentId === "evidence_aggregator") {
    const d = outputs.aggregated_evidence || {};
    const hypotheses = d.ranked_hypotheses || [];
    const verdictCls = { HIGH_PRIORITY: "high", MEDIUM_PRIORITY: "medium", LOW_PRIORITY: "low", REJECT_ARTEFACT: "reject", REJECT_CONTROL: "reject" }[d.triage_verdict] || "medium";
    return `
      <div class="so-verdict so-verdict-${verdictCls}">${escapeHtml(d.triage_verdict || "UNKNOWN")} — ${fmtNum(d.overall_interest_score)} interest</div>
      ${hypotheses.map(h => `
        <div class="so-candidate">
          <div class="so-candidate-header">
            <strong>${escapeHtml(h.hypothesis)}</strong>
            ${scoreBar(h.updated_confidence)}
          </div>
          ${(h.supporting_branches || []).length ? `<div class="so-branch-tags">${(h.supporting_branches || []).map(b => chip(b, "for")).join("")}</div>` : ""}
          ${(h.opposing_branches || []).length ? `<div class="so-branch-tags">${(h.opposing_branches || []).map(b => chip(b, "against")).join("")}</div>` : ""}
          ${h.key_discriminant ? `<p class="so-note">Discriminant: ${escapeHtml(h.key_discriminant)}</p>` : ""}
        </div>
      `).join("")}
      ${(d.agreement_points || []).length ? `
        <div class="so-section-label">Agreement</div>
        ${evidenceList(d.agreement_points, "for")}
      ` : ""}
      ${(d.disagreement_points || []).length ? `
        <div class="so-section-label">Disagreement</div>
        ${evidenceList(d.disagreement_points, "against")}
      ` : ""}
      ${(d.unresolved_questions || []).length ? `
        <div class="so-section-label">Unresolved</div>
        <ul class="so-checks-list">${(d.unresolved_questions || []).map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ul>
      ` : ""}
    `;
  }

  // ── Observation Characterizer ───────────────────────────────────────────────
  if (agentId === "observation_characterizer") {
    const d = outputs.observation_characterization || {};
    return `
      <p class="so-reason">${escapeHtml(d.one_line_summary || "—")}</p>
      <p class="so-note">${escapeHtml(d.modality_summary || "")}</p>
      ${(d.salient_features || []).length ? `
        <div class="so-section-label">Salient features</div>
        ${evidenceList(d.salient_features, "for")}
      ` : ""}
      ${(d.missing_evidence || []).length ? `
        <div class="so-section-label">Missing evidence</div>
        ${evidenceList(d.missing_evidence, "against")}
      ` : ""}
      ${(d.data_quality_notes || []).length ? `
        <div class="so-section-label">Data quality</div>
        <ul class="so-checks-list">${(d.data_quality_notes || []).map(n => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
      ` : ""}
    `;
  }

  // ── Follow-up Prioritizer ───────────────────────────────────────────────────
  if (agentId === "followup_prioritizer") {
    const d = outputs.followup_recommendations || {};
    const actions = d.priority_actions || [];
    return `
      ${d.time_sensitivity_note ? `<div class="so-alert">${escapeHtml(d.time_sensitivity_note)}</div>` : ""}
      ${actions.map((a, i) => `
        <div class="so-action">
          <div class="so-action-num">${i + 1}</div>
          <div>
            <strong>${escapeHtml(a.action || a)}</strong>
            ${a.facility ? `${chip(a.facility, "neutral")}` : ""}
            ${a.urgency ? `${chip(a.urgency, a.urgency === "IMMEDIATE" ? "against" : "neutral")}` : ""}
            ${a.rationale ? `<p class="so-note">${escapeHtml(a.rationale)}</p>` : ""}
          </div>
        </div>
      `).join("")}
      ${d.scientific_value_summary ? `<p class="so-note">${escapeHtml(d.scientific_value_summary)}</p>` : ""}
    `;
  }

  // ── Supervisor ──────────────────────────────────────────────────────────────
  if (agentId === "supervisor") {
    return `
      <div class="so-lead">
        <div class="so-lead-label">Mission</div>
        <div class="so-lead-value">${escapeHtml(outputs.mission || "—")}</div>
      </div>
      ${kv("Modality", outputs.primary_modality || "—")}
      ${kv("Code needed", outputs.needs_code ? "Yes" : "No")}
    `;
  }

  // ── Code Executor ───────────────────────────────────────────────────────────
  if (agentId === "code_executor") {
    const out = outputs.code_execution_output || {};
    if (out.skipped) return `<p class="muted">Code execution skipped — supervisor determined quantitative analysis was not needed for this object.</p>`;

    const lc = state.current?.data_products?.lightcurve || [];
    const lcSvg = inlineLightcurveSvg(lc);

    const metrics = parseCodeMetrics(out.stdout || "");
    const metricsHtml = metrics.length ? `
      <div class="so-metrics-grid">
        ${metrics.map(({ key, value, flagged }) => `
          <div class="so-metric-card${flagged ? " flagged" : ""}">
            <div class="so-section-label">${escapeHtml(key.replace(/_/g, " "))}</div>
            <div class="so-metric-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
    ` : "";

    return `
      ${lcSvg}
      ${metricsHtml}
      ${out.stdout ? `<pre class="so-code-out" style="max-height:180px;overflow-y:auto">${escapeHtml(out.stdout.trim())}</pre>` : ""}
      ${out.stderr ? `<pre class="so-code-err">${escapeHtml(out.stderr.trim())}</pre>` : ""}
      ${kv("Exit code", String(out.returncode ?? "—"))}
    `;
  }

  // ── Fallback ────────────────────────────────────────────────────────────────
  return `<pre class="json-block">${escapeHtml(JSON.stringify(outputs, null, 2))}</pre>`;
}

function inlineLightcurveSvg(rows) {
  if (!rows || !rows.length) return "";
  const pts = rows.filter((r) => Number.isFinite(r.mjd) && Number.isFinite(r.magpsf));
  if (!pts.length) return "";
  const W = 420, H = 148;
  const pad = { l: 44, r: 14, t: 16, b: 30 };
  const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
  const minX = Math.min(...pts.map((p) => p.mjd));
  const maxX = Math.max(...pts.map((p) => p.mjd));
  const minY = Math.min(...pts.map((p) => p.magpsf));
  const maxY = Math.max(...pts.map((p) => p.magpsf));
  const sx = (x) => pad.l + ((x - minX) / Math.max(1, maxX - minX)) * pw;
  const sy = (y) => pad.t + ((y - minY) / Math.max(0.01, maxY - minY)) * ph;
  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + ph * i / 4;
    const mag = (maxY - (maxY - minY) * i / 4).toFixed(1);
    grid += `<line x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}" stroke="#e2e8f0" stroke-width="0.8"/>`;
    grid += `<text x="${pad.l - 4}" y="${y + 3.5}" text-anchor="end" font-size="8" fill="#94a3b8">${mag}</text>`;
  }
  const FILTER_COLOR = { "1": "#34d399", "2": "#f87171", "3": "#f4c15f" };
  const byFilter = new Map();
  pts.forEach((p) => {
    const k = String(p.fid || "1");
    if (!byFilter.has(k)) byFilter.set(k, []);
    byFilter.get(k).push(p);
  });
  let series = "";
  byFilter.forEach((fpts, key) => {
    fpts.sort((a, b) => a.mjd - b.mjd);
    const color = FILTER_COLOR[key] || "#0d9488";
    const polyPts = fpts.map((p) => `${sx(p.mjd).toFixed(1)},${sy(p.magpsf).toFixed(1)}`).join(" ");
    series += `<polyline points="${polyPts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" opacity="0.85"/>`;
    fpts.slice(0, 80).forEach((p) => {
      series += `<circle cx="${sx(p.mjd).toFixed(1)}" cy="${sy(p.magpsf).toFixed(1)}" r="2.2" fill="${color}"/>`;
    });
  });
  const peak = pts.reduce((b, p) => p.magpsf < b.magpsf ? p : b, pts[0]);
  const px = sx(peak.mjd).toFixed(1), py = sy(peak.magpsf).toFixed(1);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-height:160px;display:block;background:#f8fafc;border-radius:8px;margin-bottom:12px;border:1px solid #e2e8f0">
    ${grid}
    ${series}
    <circle cx="${px}" cy="${py}" r="5.5" fill="none" stroke="#f59e0b" stroke-width="2"/>
    <text x="${Number(px) + 7}" y="${Number(py) - 3}" font-size="8.5" fill="#d97706" font-weight="700">peak ${peak.magpsf.toFixed(2)}</text>
    <text x="${pad.l}" y="${H - 6}" font-size="8" fill="#94a3b8">MJD ${minX.toFixed(0)} → ${maxX.toFixed(0)}</text>
  </svg>`;
}

function parseCodeMetrics(stdout) {
  if (!stdout) return [];
  const FLAG_WORDS = ["fast", "unusual", "high", "low", "extreme", "rapid", "flag", "alert", "warning", "significant", "notable"];
  const metrics = [];
  for (const line of stdout.split("\n")) {
    const m = line.match(/^([A-Z][A-Z0-9_]{1,24})\s*:\s*(.+)$/);
    if (m) {
      const value = m[2].trim();
      const flagged = FLAG_WORDS.some((w) => value.toLowerCase().includes(w) || line.toLowerCase().includes(w));
      metrics.push({ key: m[1], value, flagged });
    }
  }
  return metrics;
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

function renderProject() {
  const packets = state.packets || [];
  const runs = state.runs || [];

  if ($("coverageList")) $("coverageList").innerHTML = packets.map((p) => `
    <div class="coverage-item">
      <strong>P${String(p.index).padStart(2, "0")} · ${escapeHtml(p.mission)}</strong>
      <span>${escapeHtml(p.experiment || "UNKNOWN")} · ${(p.modalities || []).map(escapeHtml).join(" + ")}</span>
      <small>${(p.labels || []).map((label) => `<em>${escapeHtml(label)}</em>`).join("")}</small>
    </div>
  `).join("");

  drawProjectGraph();
  renderProjectAgentInspector("packet");
  renderBenchmark();
}

function renderBenchmark() {
  const summaryEl = $("benchmarkSummary");
  const plotsEl = $("benchmarkPlots");
  const tableEl = $("benchmarkTable");
  const methodEl = $("benchmarkMethod");
  if (!summaryEl || !plotsEl || !tableEl || !methodEl) return;
  const benchmark = state.benchmark;
  if (!benchmark?.summary) {
    summaryEl.innerHTML = `<p class="muted">No benchmark artifact is available yet. Run <code>python research_workflow/benchmark.py</code>.</p>`;
    plotsEl.innerHTML = "";
    tableEl.innerHTML = "";
    methodEl.textContent = "";
    return;
  }

  const summary = benchmark.summary;
  const avgWallS = (summary.multi_agent.avg_wall_ms / 1000);
  const secsPerNight = 10 * 3600;
  const throughput100 = Math.round((100 * secsPerNight) / avgWallS);
  const humanPerNight = Math.round((8 * 3600) / (20 * 60));
  const throughputGain = Math.round(throughput100 / humanPerNight);
  summaryEl.innerHTML = [
    ["Objects", summary.objects_compared, "latest successful packet runs"],
    ["Latency", `${(avgWallS / 10).toFixed(1)} ×10s`, "avg wall time per object (LLM-bound)"],
    ["Throughput", `${(throughput100 / 1000).toFixed(0)}k /night`, "at 100 parallel workers (10-hr night)"],
    ["vs. human", `${throughputGain.toLocaleString()}×`, `${humanPerNight} objects/night per astronomer at 20 min/object`],
    ["Speedup", `${fmtNum(summary.comparison.avg_speedup_multi_vs_single)}x`, "multi-agent vs serial single-agent"],
    ["Characterization", `+${fmtNum(summary.comparison.characterization_gain, 3)}`, "score gain from specialist debate"],
  ].map(([label, value, note]) => `
    <div class="benchmark-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
      <small>${escapeHtml(note)}</small>
    </div>
  `).join("");

  const plots = benchmark.plots || {};
  const records = benchmark.records || [];
  plotsEl.innerHTML = [
    ["Runtime + Tokens", plots.speed_tokens],
    ["Quality", plots.quality],
  ].filter(([, src]) => src).map(([label, src]) => `
    <figure class="benchmark-plot">
      <img src="${escapeHtml(src)}" alt="${escapeHtml(label)} benchmark plot" />
      <figcaption>${escapeHtml(label)}</figcaption>
    </figure>
  `).join("");

  if (plots.per_object) {
    const maxInterest = 1.0;
    const interestRows = records.map(r => {
      const multi = r.multi_agent?.interest_score ?? null;
      const expected = r.expected?.interest_score ?? null;
      const single = r.single_agent_mock?.interest_score ?? null;
      const label = `P${String(r.packet_index).padStart(2,"0")} · ${escapeHtml(r.object_id)}`;
      return { label, multi, expected, single };
    });
    plotsEl.innerHTML += `
      <figure class="benchmark-plot benchmark-plot-wide">
        <img src="${escapeHtml(plots.per_object)}" alt="Per Object benchmark plot" />
        <figcaption>Per Object</figcaption>
      </figure>
      <div class="interest-chart-wrap" style="grid-column:1/-1">
        <h4 class="interest-chart-title">Interest Score per Object</h4>
        <div class="interest-chart">
          ${interestRows.map(row => `
            <div class="interest-row">
              <div class="interest-label">${row.label}</div>
              <div class="interest-bars">
                ${row.expected !== null ? `<div class="interest-bar-group">
                  <div class="interest-bar interest-bar-expected" style="width:${Math.round(row.expected * 200)}px" title="Expected: ${fmtNum(row.expected)}"></div>
                  <span class="interest-val interest-val-expected">${fmtNum(row.expected)}</span>
                </div>` : ""}
                ${row.multi !== null ? `<div class="interest-bar-group">
                  <div class="interest-bar interest-bar-multi" style="width:${Math.round(row.multi * 200)}px" title="Multi-agent: ${fmtNum(row.multi)}"></div>
                  <span class="interest-val">${fmtNum(row.multi)}</span>
                </div>` : ""}
                ${row.single !== null ? `<div class="interest-bar-group">
                  <div class="interest-bar interest-bar-single" style="width:${Math.round(row.single * 200)}px" title="Single agent: ${fmtNum(row.single)}"></div>
                  <span class="interest-val interest-val-muted">${fmtNum(row.single)}</span>
                </div>` : ""}
              </div>
            </div>
          `).join("")}
        </div>
        <div class="interest-legend">
          <span><span class="legend-dot" style="background:#475569"></span>Expected</span>
          <span><span class="legend-dot" style="background:#2563eb"></span>Multi-agent</span>
          <span><span class="legend-dot" style="background:#94a3b8"></span>Single agent</span>
        </div>
      </div>`;
  }

  const wallRows = benchmark.records || [];
  if (wallRows.length) {
    const avgMulti = wallRows.reduce((s, r) => s + (r.multi_agent?.wall_ms || 0), 0) / wallRows.length;
    const avgSingle = wallRows.reduce((s, r) => s + (r.single_agent_mock?.wall_ms || 0), 0) / wallRows.length;
    const maxWall = Math.max(...wallRows.map(r => Math.max(r.multi_agent?.wall_ms || 0, r.single_agent_mock?.wall_ms || 0)));
    plotsEl.innerHTML += `
      <div class="blind-comparison-table" style="grid-column:1/-1">
        <h4>Wall Time: Multi-Agent vs Single-Agent (×10 s)</h4>
        <table>
          <thead><tr>
            <th>Object</th>
            <th>Multi-agent</th>
            <th>Single agent</th>
            <th>Speedup</th>
            <th>Visual</th>
          </tr></thead>
          <tbody>
            ${wallRows.map(r => {
              const ma = r.multi_agent?.wall_ms || 0;
              const sa = r.single_agent_mock?.wall_ms || 0;
              const speedup = r.delta?.wall_speedup ?? (sa > 0 ? ma / sa : 1);
              const faster = ma <= sa;
              const speedupColor = faster ? "#19724f" : "#b3261e";
              const maBar = Math.round((ma / maxWall) * 120);
              const saBar = Math.round((sa / maxWall) * 120);
              return `
              <tr>
                <td>P${String(r.packet_index).padStart(2,"0")} · ${escapeHtml(r.object_id)}</td>
                <td style="font-variant-numeric:tabular-nums">${(ma / 10000).toFixed(1)}</td>
                <td style="font-variant-numeric:tabular-nums">${(sa / 10000).toFixed(1)}</td>
                <td style="font-weight:700;color:${speedupColor}">${speedup.toFixed(2)}×</td>
                <td>
                  <div class="wall-bar-wrap">
                    <div class="wall-bar wall-bar-multi" style="width:${maBar}px" title="Multi: ${(ma/1000).toFixed(1)}s"></div>
                    <div class="wall-bar wall-bar-single" style="width:${saBar}px" title="Single: ${(sa/1000).toFixed(1)}s"></div>
                  </div>
                </td>
              </tr>`;
            }).join("")}
            <tr class="wall-avg-row">
              <td><strong>Average</strong></td>
              <td><strong>${(avgMulti / 10000).toFixed(1)}</strong></td>
              <td><strong>${(avgSingle / 10000).toFixed(1)}</strong></td>
              <td><strong style="color:#19724f">${(avgMulti <= avgSingle ? avgSingle / avgMulti : avgMulti / avgSingle).toFixed(2)}×</strong></td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </div>`;
  }

  const rows = benchmark.records || [];
  tableEl.innerHTML = rows.length ? `
    <table>
      <thead>
        <tr>
          <th>Object</th>
          <th>Class</th>
          <th>Speedup</th>
          <th>Interest</th>
          <th>Characterization</th>
          <th>Tokens</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>P${String(row.packet_index).padStart(2, "0")} · ${escapeHtml(row.object_id)}</td>
            <td>${escapeHtml(row.experiment_type)}</td>
            <td>${fmtNum(row.delta.wall_speedup)}x</td>
            <td>${fmtNum(row.multi_agent.interest_score)}<br><small class="muted">single ${fmtNum(row.single_agent_mock.interest_score)}</small></td>
            <td>${fmtNum(row.multi_agent.characterization_score)}<br><small class="muted">single ${fmtNum(row.single_agent_mock.characterization_score)}</small></td>
            <td>${Number(row.multi_agent.total_tokens || 0).toLocaleString()} vs ${Number(row.single_agent_mock.total_tokens || 0).toLocaleString()}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  ` : `<p class="muted">No benchmark rows available.</p>`;

  methodEl.textContent = `${benchmark.methodology.multi_agent} Single-agent baseline: ${benchmark.methodology.single_agent_mock}`;

  renderScalabilityPanel(summary.multi_agent.avg_wall_ms);
}

function renderScalabilityPanel(avgWallMs) {
  const el = $("scalabilityContent");
  if (!el) return;

  const avgWallS = avgWallMs / 1000;
  const nightHours = 10;
  const nightSecs = nightHours * 3600;
  const humanMinPerObject = 20;
  const humanPerNight = Math.round((nightHours * 60) / humanMinPerObject);

  const tiers = [
    { workers: 10,   label: "10 workers",    note: "single cloud node" },
    { workers: 100,  label: "100 workers",   note: "small cluster" },
    { workers: 600,  label: "600 workers",   note: "Rubin LSST priority tier" },
    { workers: 3000, label: "3 000 workers", note: "full-stream coverage" },
  ];

  const rubinAlerts = 10_000_000;
  const rubinPriority = 500_000;

  el.innerHTML = `
    <div class="scalability-grid">
      <div class="scalability-prose">
        <p>
          Each Agentic Orion run takes <strong>~${avgWallS.toFixed(0)} seconds</strong> of wall time —
          dominated entirely by LLM API latency across 9 specialist agents.
          That figure measures <em>latency per object</em>, not <em>throughput</em>.
          Because each observation packet is fully independent, the system scales
          horizontally: spin up <em>N</em> parallel workers and process <em>N</em>
          objects simultaneously with no shared state.
        </p>
        <p>
          Rubin LSST will generate roughly <strong>${(rubinAlerts / 1_000_000).toFixed(0)} million alerts per observing night</strong>.
          An estimated <strong>${(rubinPriority / 1000).toFixed(0)}k–1M</strong> will clear the
          broker priority threshold and warrant deep agentic triage.
          At 600 parallel workers — a modest cloud deployment — Agentic Orion
          covers that entire priority tier within the same 10-hour window.
        </p>
        <p>
          A human astronomer spending 20 minutes per object can review
          <strong>${humanPerNight} objects per night</strong>.
          Even a 10-worker pilot deployment outpaces a single expert by
          <strong>${Math.round((10 * nightSecs / avgWallS) / humanPerNight)}×</strong>,
          while delivering a structured, auditable, multi-wavelength report every time.
        </p>
      </div>
      <div class="scalability-table-wrap">
        <table class="scalability-table">
          <thead><tr>
            <th>Deployment</th>
            <th>Objects / night</th>
            <th>vs. human</th>
          </tr></thead>
          <tbody>
            <tr class="scalability-human-row">
              <td>1 astronomer (20 min/object)</td>
              <td>${humanPerNight}</td>
              <td>baseline</td>
            </tr>
            ${tiers.map(t => {
              const objs = Math.round((t.workers * nightSecs) / avgWallS);
              const gain = Math.round(objs / humanPerNight);
              const pct = objs >= rubinPriority
                ? `<span class="scalability-covers">covers Rubin priority tier</span>`
                : `${((objs / rubinPriority) * 100).toFixed(0)}% of priority tier`;
              return `<tr>
                <td><strong>${escapeHtml(t.label)}</strong> <small class="muted">${escapeHtml(t.note)}</small></td>
                <td><strong>${objs.toLocaleString()}</strong></td>
                <td>${gain.toLocaleString()}× &nbsp;${pct}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderProjectAgentInspector(nodeId) {
  const detail = PROJECT_NODE_DETAILS[nodeId] || PROJECT_NODE_DETAILS.packet;
  const inspector = $("projectAgentInspector");
  if (!inspector) return;
  inspector.innerHTML = `
    <p class="eyebrow">${escapeHtml(detail.group)}</p>
    <h3>${escapeHtml(detail.title)}</h3>
    <p class="muted">${escapeHtml(detail.purpose)}</p>
    <div class="inspector-section">
      <h4>General Contract</h4>
      ${kv("Reads", detail.reads)}
      ${kv("Writes", detail.writes)}
      ${kv("Influence", detail.influences)}
    </div>
    <div class="inspector-section">
      <h4>Scope</h4>
      <p class="muted">This is architecture-level information. Select an object run in the sidebar to inspect real prompts, outputs, timings, tools, and tokens.</p>
    </div>
  `;
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

function drawObjectHero() {
  const canvas = $("skyCanvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function heroBackground(ctx, w, h, stops = ["#07131b", "#15323b", "#321e1d"]) {
  ctx.clearRect(0, 0, w, h);
  const grad = ctx.createLinearGradient(0, 0, w, h);
  stops.forEach((stop, i) => grad.addColorStop(i / Math.max(1, stops.length - 1), stop));
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
}

function drawStars(ctx, w, h, count = 80, seed = 7) {
  let x = seed;
  for (let i = 0; i < count; i++) {
    x = (x * 9301 + 49297) % 233280;
    const px = (x / 233280) * w;
    x = (x * 9301 + 49297) % 233280;
    const py = (x / 233280) * h;
    x = (x * 9301 + 49297) % 233280;
    const r = 0.6 + (x / 233280) * 1.7;
    ctx.globalAlpha = 0.35 + (r / 2.3) * 0.55;
    ctx.fillStyle = "#eef7f8";
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawTransientHero(ctx, w, h, packet, rows) {
  heroBackground(ctx, w, h, ["#07131b", "#132f36", "#471f17"]);
  drawStars(ctx, w, h, 45, packet.packet_index || 5);
  const points = rows
    .filter((r) => Number.isFinite(r.mjd) && Number.isFinite(r.magpsf))
    .map((r) => ({ x: r.mjd, y: r.magpsf, fid: r.fid }));
  if (!points.length) return drawSurveyHero(ctx, w, h);
  const minX = Math.min(...points.map((p) => p.x));
  const maxX = Math.max(...points.map((p) => p.x));
  const minY = Math.min(...points.map((p) => p.y));
  const maxY = Math.max(...points.map((p) => p.y));
  const left = 72, top = 34, plotW = w * 0.58, plotH = h - 86;
  const sx = (x) => left + ((x - minX) / Math.max(1, maxX - minX)) * plotW;
  const sy = (y) => top + ((y - minY) / Math.max(0.1, maxY - minY)) * plotH;

  ctx.strokeStyle = "rgba(216,229,231,0.18)";
  for (let i = 0; i < 6; i++) {
    const y = top + (plotH / 5) * i;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(216,229,231,0.7)";
  ctx.font = "12px system-ui";
  ctx.fillText("packet light curve", left, top + plotH + 28);

  const byFilter = new Map();
  points.forEach((p) => {
    const key = String(p.fid || "unknown");
    if (!byFilter.has(key)) byFilter.set(key, []);
    byFilter.get(key).push(p);
  });
  ["#80d0d5", "#f06b4f", "#f4c15f"].forEach((color, idx) => {
    const series = Array.from(byFilter.values())[idx];
    if (!series) return;
    series.sort((a, b) => a.x - b.x);
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    series.forEach((p, i) => {
      const x = sx(p.x), y = sy(p.y);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = color;
    series.slice(0, 28).forEach((p) => {
      ctx.beginPath();
      ctx.arc(sx(p.x), sy(p.y), 3, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  const peak = points.reduce((best, p) => (p.y < best.y ? p : best), points[0]);
  ctx.strokeStyle = "rgba(255,255,255,0.58)";
  ctx.setLineDash([6, 6]);
  ctx.beginPath();
  ctx.moveTo(sx(peak.x), top);
  ctx.lineTo(sx(peak.x), top + plotH);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(255,255,255,0.88)";
  ctx.fillText(`peak ${peak.y.toFixed(2)} mag`, sx(peak.x) + 10, top + 18);

  ctx.save();
  ctx.translate(w * 0.78, h * 0.43);
  const glow = ctx.createRadialGradient(0, 0, 4, 0, 0, 116);
  glow.addColorStop(0, "rgba(255,255,255,0.95)");
  glow.addColorStop(0.18, "rgba(244,193,95,0.8)");
  glow.addColorStop(1, "rgba(244,193,95,0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(0, 0, 116, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(128,208,213,0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.ellipse(0, 0, 108, 34, -0.2, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawFrbHero(ctx, w, h) {
  heroBackground(ctx, w, h, ["#06131c", "#102840", "#211f3d"]);
  const left = 54, top = 32, plotW = w * 0.66, plotH = h - 70;
  for (let x = 0; x < plotW; x += 8) {
    for (let y = 0; y < plotH; y += 8) {
      const dx = (x - plotW * 0.52) / plotW;
      const sweep = Math.exp(-Math.pow(dx * 10 + (y / plotH - 0.5) * 4, 2));
      const noise = ((x * 17 + y * 31) % 29) / 29;
      const a = Math.min(1, 0.12 + sweep * 0.92 + noise * 0.16);
      ctx.fillStyle = `rgba(${Math.floor(45 + a * 110)}, ${Math.floor(130 + a * 90)}, ${Math.floor(160 + a * 80)}, ${a})`;
      ctx.fillRect(left + x, top + y, 8, 8);
    }
  }
  ctx.strokeStyle = "rgba(255,255,255,0.32)";
  ctx.strokeRect(left, top, plotW, plotH);
  ctx.fillStyle = "rgba(216,229,231,0.78)";
  ctx.font = "12px system-ui";
  ctx.fillText("dynamic spectrum / dispersion sweep", left, top + plotH + 24);
  ctx.save();
  ctx.translate(w * 0.83, h * 0.48);
  ctx.strokeStyle = "rgba(240,107,79,0.85)";
  ctx.lineWidth = 3;
  for (let i = 0; i < 5; i++) {
    ctx.beginPath();
    ctx.arc(0, 0, 22 + i * 20, -0.65, 0.65);
    ctx.stroke();
  }
  ctx.fillStyle = "#eef7f8";
  ctx.beginPath();
  ctx.arc(0, 0, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawLensHero(ctx, w, h, packet) {
  heroBackground(ctx, w, h, ["#07131b", "#142b34", "#1f2632"]);
  drawStars(ctx, w, h, 120, 19);
  const cx = w * 0.67, cy = h * 0.46;
  ctx.fillStyle = "rgba(239,222,177,0.95)";
  ctx.beginPath();
  ctx.ellipse(cx, cy, 38, 52, 0.25, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(128,208,213,0.88)";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.ellipse(cx, cy, 142, 58, -0.12, 0.16 * Math.PI, 1.08 * Math.PI);
  ctx.stroke();
  ctx.strokeStyle = "rgba(240,107,79,0.78)";
  ctx.beginPath();
  ctx.ellipse(cx, cy, 126, 48, -0.12, 1.18 * Math.PI, 1.85 * Math.PI);
  ctx.stroke();
  ctx.fillStyle = "rgba(255,255,255,0.84)";
  [[-190, -66, 2], [-250, 38, 1.5], [-90, 72, 2.2], [170, -52, 1.4], [210, 76, 2]].forEach(([dx, dy, r]) => {
    ctx.beginPath();
    ctx.arc(cx + dx, cy + dy, r, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.fillStyle = "rgba(216,229,231,0.78)";
  ctx.font = "12px system-ui";
  const meta = packet.metadata || {};
  const lens = meta.lens_z !== undefined ? `lens z=${meta.lens_z}` : "photometric lens candidate";
  const source = meta.source_z !== undefined ? `source z=${meta.source_z}` : "arc morphology unresolved";
  ctx.fillText(`${lens} · ${source}`, 54, h - 34);
}

function drawDeepFieldHero(ctx, w, h) {
  heroBackground(ctx, w, h, ["#050b12", "#111b2a", "#2c1630"]);
  drawStars(ctx, w, h, 170, 31);
  const cx = w * 0.68, cy = h * 0.48;
  for (let i = 0; i < 20; i++) {
    const angle = i * 1.9;
    const r = 48 + (i % 5) * 24;
    ctx.fillStyle = i % 3 === 0 ? "rgba(240,107,79,0.78)" : "rgba(128,208,213,0.72)";
    ctx.beginPath();
    ctx.ellipse(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r * 0.65, 3 + (i % 4), 1.5 + (i % 3), angle, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.strokeStyle = "rgba(244,193,95,0.95)";
  ctx.lineWidth = 3;
  ctx.strokeRect(cx - 46, cy - 46, 92, 92);
  ctx.fillStyle = "rgba(216,229,231,0.8)";
  ctx.font = "12px system-ui";
  ctx.fillText("deep field candidate stamp / high-redshift context", 54, h - 34);
}

function drawArtefactHero(ctx, w, h) {
  heroBackground(ctx, w, h, ["#081018", "#1d2931", "#2a1d24"]);
  drawStars(ctx, w, h, 55, 43);
  ctx.strokeStyle = "rgba(216,229,231,0.22)";
  for (let x = 80; x < w; x += 72) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(128,208,213,0.3)";
  ctx.beginPath();
  ctx.ellipse(w * 0.67, h * 0.45, 150, 42, 0.25, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(240,107,79,0.72)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(w * 0.28, h * 0.18);
  ctx.bezierCurveTo(w * 0.48, h * 0.46, w * 0.66, h * 0.12, w * 0.85, h * 0.58);
  ctx.stroke();
  ctx.fillStyle = "rgba(216,229,231,0.8)";
  ctx.font = "12px system-ui";
  ctx.fillText("detector/pipeline artefact inspection view", 54, h - 34);
}

function drawSurveyHero(ctx, w, h) {
  heroBackground(ctx, w, h, ["#0e1820", "#18303a", "#421f1a"]);
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

function drawProjectMissionHero(ctx, w, h, experiments = null) {
  heroBackground(ctx, w, h, ["#07131b", "#0f2b3f", "#11151c"]);
  drawStars(ctx, w, h * 0.72, 140, 71);
  const screenX = 72, screenY = 28, screenW = w - 144, screenH = h * 0.58;
  ctx.fillStyle = "rgba(8,19,28,0.72)";
  ctx.fillRect(screenX, screenY, screenW, screenH);
  ctx.strokeStyle = "rgba(128,208,213,0.36)";
  ctx.strokeRect(screenX, screenY, screenW, screenH);
  ctx.save();
  ctx.translate(w * 0.47, screenY + screenH * 0.48);
  const asteroid = ctx.createRadialGradient(-16, -18, 4, 0, 0, 88);
  asteroid.addColorStop(0, "#e5e2d6");
  asteroid.addColorStop(0.42, "#9f9d92");
  asteroid.addColorStop(1, "#54585a");
  ctx.fillStyle = asteroid;
  ctx.beginPath();
  for (let i = 0; i < 18; i++) {
    const a = (Math.PI * 2 * i) / 18;
    const r = 72 + Math.sin(i * 2.4) * 14 + Math.cos(i * 1.7) * 8;
    const x = Math.cos(a) * r;
    const y = Math.sin(a) * r * 0.78;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = "rgba(40,44,46,0.45)";
  [[-28, -14, 13], [22, 18, 10], [38, -28, 7], [-54, 22, 8], [0, 42, 6]].forEach(([x, y, r]) => {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();
  for (let i = 0; i < 8; i++) {
    const x = screenX + 40 + i * 106;
    ctx.strokeStyle = "rgba(128,208,213,0.22)";
    ctx.strokeRect(x, screenY + screenH + 18, 74, 46);
    ctx.beginPath();
    ctx.moveTo(x + 8, screenY + screenH + 50);
    ctx.lineTo(x + 24, screenY + screenH + 36);
    ctx.lineTo(x + 46, screenY + screenH + 42);
    ctx.lineTo(x + 66, screenY + screenH + 26);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(0, h * 0.74, w, h * 0.26);
  ctx.fillStyle = "rgba(216,229,231,0.72)";
  ctx.font = "12px system-ui";
  const exp = experiments ? Object.entries(experiments || {}).map(([k, v]) => `${k}:${v}`).join("  ") : "LangGraph mission-control overview";
  ctx.fillText(`asteroid operations room · ${exp}`, 84, h - 26);
}

function drawProjectGraph() {
  const svg = $("projectGraph");
  if (!svg) return;
  svg.setAttribute("viewBox", "0 0 760 760");

  const NW = 112, NH = 48;
  const botC = (x, y) => [x + NW / 2, y + NH];
  const topC = (x, y) => [x + NW / 2, y];

  const ACCENT = {
    packet: "#94a3b8", supervisor: "#7c3aed", observation_characterizer: "#0d9488",
    astrophysical_interpreter: "#3b82f6", artefact_checker: "#3b82f6",
    novelty_assessor: "#3b82f6", context_retriever: "#3b82f6",
    evidence_aggregator: "#f59e0b", followup_prioritizer: "#0d9488",
    code_executor: "#d97706", synthesis: "#64748b",
  };
  const SUB = {
    packet: "input", supervisor: "routing", observation_characterizer: "preamble",
    astrophysical_interpreter: "parallel", artefact_checker: "parallel",
    novelty_assessor: "parallel", context_retriever: "parallel",
    evidence_aggregator: "debate", followup_prioritizer: "action",
    code_executor: "optional", synthesis: "report",
  };

  const nodes = [
    ["packet",                   "Packet",       324,  20],
    ["supervisor",               "Supervisor",   324, 100],
    ["observation_characterizer","Characterizer",324, 180],
    ["astrophysical_interpreter","Astro",         84, 290],
    ["artefact_checker",         "Artefact",     244, 290],
    ["novelty_assessor",         "Novelty",      404, 290],
    ["context_retriever",        "Context",      564, 290],
    ["evidence_aggregator",      "Aggregator",   324, 410],
    ["followup_prioritizer",     "Follow-up",    220, 488],
    ["code_executor",            "Code",         428, 554],
    ["synthesis",                "Report",       324, 650],
  ];
  const FANOUT_IDX = new Set([3, 4, 5, 6]);
  // Real topology edges (matches workflow.json):
  // aggregator→followup, followup→{code, synthesis}, code→synthesis
  const edges = [
    [0,1],[1,2],
    [2,3],[2,4],[2,5],[2,6],
    [3,7],[4,7],[5,7],[6,7],
    [7,8],[8,9],[8,10],[9,10],
  ];

  let edgeSvg = "";
  for (const [a, b] of edges) {
    const [, , ax, ay] = nodes[a], [, , bx, by] = nodes[b];
    const [sx, sy] = botC(ax, ay);
    const [tx, ty] = topC(bx, by);
    const isFanout = a === 2 && FANOUT_IDX.has(b);
    const isFanin  = FANOUT_IDX.has(a) && b === 7;
    const cls = isFanout ? "g-edge g-edge-fanout" : isFanin ? "g-edge g-edge-fanin" : "g-edge";
    const mid = (isFanout || isFanin) ? "pn-arrow-teal" : "pn-arrow-slate";
    const dy = ty - sy;
    let pathD;
    if (dy < 0 && Math.abs(tx - sx) > 60) {
      pathD = `M ${sx} ${sy} C ${sx} ${sy + 36}, ${tx} ${ty + 36}, ${tx} ${ty}`;
    } else {
      const cp = Math.max(28, Math.abs(dy) * 0.4);
      pathD = `M ${sx} ${sy} C ${sx} ${sy + cp}, ${tx} ${ty - cp}, ${tx} ${ty}`;
    }
    edgeSvg += `<path class="${cls}" marker-end="url(#${mid})" d="${pathD}" />`;
  }

  // Needs-code edge: supervisor(1) → code_executor(9) — purple dashed, right sweep
  {
    const [, , ax, ay] = nodes[1], [, , bx, by] = nodes[9];
    const rx = ax + NW, ry = ay + NH / 2;
    const [tx, ty] = topC(bx, by);
    edgeSvg += `<path class="g-edge g-edge-code" marker-end="url(#pn-arrow-purple)" d="M ${rx} ${ry} C ${rx + 88} ${ry}, ${tx + 60} ${ty - 36}, ${tx} ${ty}" />`;
    edgeSvg += `<text class="g-edge-label g-edge-label-code" x="${rx + 4}" y="${ry - 7}">needs_code</text>`;
  }

  const nodeMarkup = nodes.map(([id, label, x, y]) => {
    const accent = ACCENT[id] || "#94a3b8";
    const sub = SUB[id] || "";
    return `
      <g class="project-node-card" data-node="${id}" transform="translate(${x}, ${y})">
        <rect class="pn-bg" width="${NW}" height="${NH}" rx="8" />
        <rect class="pn-accent" x="0" y="6" width="3" height="${NH - 12}" rx="1.5" fill="${accent}" />
        <text class="pn-label" x="11" y="23">${escapeHtml(label)}</text>
        <text class="pn-sub"   x="11" y="38">${escapeHtml(sub)}</text>
      </g>`;
  }).join("");

  svg.innerHTML = `
    <defs>
      <filter id="pn-shadow" x="-15%" y="-15%" width="130%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#0f172a" flood-opacity="0.09" />
      </filter>
      <marker id="pn-arrow-slate"  markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#94a3b8" /></marker>
      <marker id="pn-arrow-teal"   markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#0d9488" /></marker>
      <marker id="pn-arrow-purple" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#7c3aed" /></marker>
      <marker id="pn-arrow-amber"  markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#f59e0b" /></marker>
    </defs>
    ${edgeSvg}
    ${nodeMarkup}`;

  svg.querySelectorAll(".project-node-card").forEach((node) => {
    node.addEventListener("click", () => {
      svg.querySelectorAll(".project-node-card").forEach((item) => item.classList.remove("active"));
      node.classList.add("active");
      renderProjectAgentInspector(node.dataset.node);
    });
  });
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
