/* PlotGenre single-page UI.
 * Talks to the backend only through the frontend server's REST proxy
 * (/api/gateway/... and /api/pipeline/...), whose targets are configurable.
 */
(function () {
  "use strict";

  const CFG = window.PLOTGENRE_CONFIG || { apiBase: "/api" };
  const MIN_WORDS = 5;
  const GRAFANA_PANELS = [
    { id: 1, title: "Requests per second" },
    { id: 2, title: "Latency p95" },
    { id: 4, title: "Predicted genres" },
    { id: 5, title: "Live input drift" },
    { id: 7, title: "Pipeline throughput" },
    { id: 11, title: "Batch drift score" },
  ];
  const SAMPLES = [
    { label: "Haunted lighthouse", text: "A widowed engineer takes a job restoring an abandoned lighthouse on a remote island. At night she hears footsteps on the spiral stairs and finds messages scratched into the walls that seem to predict her own death. The islanders refuse to talk about the keeper who vanished there forty years ago, and as a storm cuts off the island she realises something in the tower wants her to stay forever." },
    { label: "Bank heist", text: "Four old friends who grew up in the docks plan one last robbery of a private bank that launders money for a ruthless crime family. The safecracker is a recovering gambler, the driver owes money to everyone and the planner is secretly working with a detective. When the job goes wrong, they have one night to escape the city while the police and the mob close in on them." },
    { label: "Space rescue", text: "In the year 2190 a mining crew on a distant moon receives a distress signal from a research station that was supposed to be empty. Their captain, an ex-soldier haunted by a failed mission, leads the team through the frozen tunnels, where they discover an alien life form that copies whatever it touches. With their oxygen running out they must decide who to trust before the creature reaches their ship." },
    { label: "Wedding mix-up", text: "A nervous florist is mistaken for the wedding planner at a lavish ceremony and, too embarrassed to admit the error, tries to run the whole event. Things get worse when she falls for the bride's charming brother, the real planner arrives, and a goat eats the cake. Her family, friends and an eccentric priest help her keep the chaos hidden until the final dance." },
  ];

  // ------------------------------------------------------------------ utilities
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const genreVar = (g) => `var(--g-${String(g).replace(/\s+/g, "_")}, #5A6880)`;
  const countWords = (t) => (t.trim() ? t.trim().split(/\s+/).length : 0);
  const fmtTime = (iso) => { if (!iso) return "–"; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(); };
  const fmtDur = (s) => (s == null ? "–" : s < 60 ? `${Number(s).toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);
  let currentPage = "classify";

  function telemetry(event) {
    try {
      const body = JSON.stringify({ page: currentPage, ...event });
      if (navigator.sendBeacon) navigator.sendBeacon("/telemetry", new Blob([body], { type: "application/json" }));
      else fetch("/telemetry", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true });
    } catch (_) { /* telemetry must never break the UI */ }
  }
  window.addEventListener("error", (e) => telemetry({ type: "ui_error", name: "js_error", detail: String(e.message).slice(0, 300) }));
  window.addEventListener("unhandledrejection", (e) => telemetry({ type: "ui_error", name: "promise", detail: String(e.reason).slice(0, 300) }));

  class ApiError extends Error {
    constructor(message, code, status) { super(message); this.code = code; this.status = status; }
  }

  async function api(target, path, { method = "GET", body, timeoutMs = 20000 } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(`${CFG.apiBase}/${target}/${path}`, {
        method, signal: ctrl.signal,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON */ }
      if (!res.ok) {
        const err = (data && data.error) || {};
        throw new ApiError(err.message || `Request failed (${res.status}).`, err.code || "http_error", res.status);
      }
      return data;
    } catch (e) {
      if (e.name === "AbortError") throw new ApiError("The server took too long to answer. Please try again.", "timeout", 0);
      if (e instanceof ApiError) throw e;
      throw new ApiError("Cannot reach PlotGenre. Check your connection and that the services are running.", "network", 0);
    } finally { clearTimeout(timer); }
  }

  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3500);
  }

  function confirmDialog(title, html, okLabel) {
    const d = $("#dialog");
    $("#dialog-title").textContent = title; $("#dialog-body").innerHTML = html;
    $("#dialog-ok").textContent = okLabel || "OK"; $("#dialog-cancel").hidden = !okLabel;
    return new Promise((resolve) => {
      d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true });
      d.showModal();
    });
  }

  // ------------------------------------------------------------------ routing
  const views = ["classify", "pipeline", "help"];
  let pipelineTimer = null;
  function route() {
    const name = (location.hash.replace(/^#\/?/, "") || "classify").split("?")[0];
    const page = views.includes(name) ? name : "classify";
    currentPage = page;
    views.forEach((v) => { $(`#view-${v}`).hidden = v !== page; });
    document.querySelectorAll(".tabs a").forEach((a) => {
      if (a.dataset.route === page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.title = { classify: "PlotGenre – classify a plot", pipeline: "PlotGenre – pipeline console", help: "PlotGenre – help" }[page];
    clearInterval(pipelineTimer);
    if (page === "pipeline") { loadPipeline(); pipelineTimer = setInterval(loadPipeline, 8000); }
    telemetry({ type: "page_load", duration_ms: Math.round(performance.now()) });
  }
  window.addEventListener("hashchange", route);

  // ------------------------------------------------------------------ service status
  async function checkService() {
    const box = $("#service-status");
    try {
      await api("gateway", "ready", { timeoutMs: 6000 });
      box.className = "service up"; box.querySelector(".label").textContent = "Model ready";
    } catch (e) {
      box.className = "service down";
      box.querySelector(".label").textContent = e.status === 503 ? "Model starting…" : "Service offline";
    }
  }

  // ------------------------------------------------------------------ classify page
  const plot = $("#plot"), btn = $("#predict-btn");
  function onInput() {
    const n = countWords(plot.value);
    const c = $("#plot-count");
    c.textContent = `${n} word${n === 1 ? "" : "s"}`;
    c.classList.toggle("ok", n >= 30);
    btn.disabled = n < MIN_WORDS;
  }
  plot.addEventListener("input", onInput);
  plot.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !btn.disabled) predict(); });
  btn.addEventListener("click", predict);
  $("#clear-btn").addEventListener("click", () => { plot.value = ""; onInput(); showState("empty"); plot.focus(); });

  const list = $("#sample-list");
  SAMPLES.forEach((s) => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = s.label;
    b.addEventListener("click", () => { plot.value = s.text; onInput(); telemetry({ type: "action", name: "sample" }); predict(); });
    list.appendChild(b);
  });

  function showState(state, message) {
    $("#results-empty").hidden = state !== "empty";
    $("#results-loading").hidden = state !== "loading";
    $("#results-body").hidden = state !== "result";
    const err = $("#results-error");
    err.hidden = state !== "error";
    if (state === "error") {
      err.innerHTML = `${esc(message)} <button class="btn small secondary" type="button" id="retry-btn">Try again</button>`;
      $("#retry-btn").addEventListener("click", predict);
    }
  }

  let inFlight = false;
  async function predict() {
    if (inFlight) return;
    const text = plot.value.trim();
    if (countWords(text) < MIN_WORDS) { showState("error", `Please write at least ${MIN_WORDS} words about the plot.`); return; }
    inFlight = true; btn.disabled = true; btn.textContent = "Finding genres…";
    showState("loading");
    telemetry({ type: "action", name: "predict" });
    try {
      const res = await api("gateway", "api/v1/predict", { method: "POST", body: { text, top_k: 3, explain: true } });
      renderResult(text, res);
      showState("result");
    } catch (e) {
      telemetry({ type: "ui_error", name: e.code || "predict_failed", detail: e.message });
      showState("error", e.message);
    } finally {
      inFlight = false; btn.textContent = "Find genres"; onInput();
    }
  }

  function renderResult(text, res) {
    const chips = $("#predicted-chips");
    const byGenre = Object.fromEntries(res.genres.map((g) => [g.genre, g]));
    chips.innerHTML = res.predicted_genres.map((g) =>
      `<li class="chip" style="background:${genreVar(g)}">✓ ${esc(g)} <span class="pct">${Math.round(byGenre[g].confidence * 100)}%</span></li>`).join("");

    const warn = $("#results-warnings");
    warn.hidden = !res.warnings.length;
    warn.innerHTML = res.warnings.map(esc).join("<br>");

    const thr = res.model && res.model.threshold != null ? res.model.threshold : 0.5;
    $("#genre-bars").innerHTML = res.genres.map((g) => {
      const pct = Math.round(g.confidence * 100);
      return `<li class="bar ${g.predicted ? "on" : ""}">
        <span class="name"><i class="swatch" style="background:${genreVar(g.genre)}"></i>${esc(g.genre)}${g.predicted ? '<span class="sr"> (suggested)</span>' : ""}</span>
        <span class="track" role="progressbar" aria-label="${esc(g.genre)} confidence" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
          <span class="bar-fill" style="width:${pct}%"></span><span class="thr" style="left:${thr * 100}%" title="Suggestion threshold ${Math.round(thr * 100)}%"></span>
        </span>
        <span class="val">${pct}%</span></li>`;
    }).join("");

    // Highlight influential words in the user's own text.
    const best = {};
    (res.keywords || []).forEach((k) => { if (!best[k.word] || best[k.word].weight < k.weight) best[k.word] = k; });
    const single = Object.keys(best).filter((w) => !w.includes(" "));
    let html = esc(text);
    if (single.length) {
      const re = new RegExp(`\\b(${single.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`, "gi");
      html = html.replace(re, (m) => {
        const k = best[m.toLowerCase()];
        return k ? `<mark style="background:${genreVar(k.genre)}" title="${esc(k.genre)}">${m}</mark>` : m;
      });
    }
    const phrases = Object.keys(best).filter((w) => w.includes(" "));
    $("#annotated").innerHTML = html + (phrases.length
      ? `<p class="hint">Key phrases: ${phrases.map((p) => `<mark style="background:${genreVar(best[p].genre)}">${esc(p)}</mark>`).join(" ")}</p>` : "");
    const m = res.model || {};
    $("#result-meta").textContent =
      `Model: ${m.algorithm || m.name}${m.version ? `, version ${m.version}` : ""}. Answered in ${Math.round(res.latency_ms)} ms. Reference: ${res.request_id}.`;
  }

  // ------------------------------------------------------------------ pipeline page
  const STATUS_FILL = { success: ["#D7EFEA", "#16766E"], failed: ["#FBE9E7", "#B3261E"], running: ["#FFF1D1", "#D9961A"], never_run: ["#EEF1F5", "#9AA6B8"] };

  function renderDag(dag, runningStages) {
    const svg = $("#dag");
    const order = topoOrder(dag);
    const w = 132, h = 64, gapX = 28;
    const width = order.length * (w + gapX) + 20;
    svg.setAttribute("viewBox", `0 0 ${width} 190`);
    const pos = {}; order.forEach((id, i) => { pos[id] = { x: 10 + i * (w + gapX), y: 50 }; });
    const nodes = Object.fromEntries(dag.nodes.map((n) => [n.id, n]));
    let out = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#5A6880"/></marker></defs>`;
    dag.edges.forEach((e) => {
      const a = pos[e.from], b = pos[e.to]; if (!a || !b) return;
      const adjacent = order.indexOf(e.to) - order.indexOf(e.from) === 1;
      if (adjacent) out += `<line x1="${a.x + w}" y1="${a.y + h / 2}" x2="${b.x - 3}" y2="${b.y + h / 2}" stroke="#5A6880" stroke-width="1.6" marker-end="url(#arrow)"/>`;
      else {
        const mx1 = a.x + w / 2, mx2 = b.x + w / 2, top = 22 + (order.indexOf(e.to) - order.indexOf(e.from)) * 3;
        out += `<path d="M${mx1} ${a.y} C${mx1} ${top - 20}, ${mx2} ${top - 20}, ${mx2} ${b.y - 3}" fill="none" stroke="#9AA6B8" stroke-width="1.3" stroke-dasharray="4 3" marker-end="url(#arrow)"/>`;
      }
    });
    order.forEach((id, i) => {
      const n = nodes[id], p = pos[id];
      const st = runningStages && runningStages.has(id) ? "running" : n.status in STATUS_FILL ? n.status : "never_run";
      const [fill, stroke] = STATUS_FILL[st];
      const sub = n.duration_s != null ? `${fmtDur(n.duration_s)}${n.throughput_rps ? `, ${Math.round(n.throughput_rps).toLocaleString()} rows/s` : ""}` : "not run yet";
      const tip = `${id}: ${st.replace("_", " ")}${n.rows ? `, ${n.rows.toLocaleString()} rows` : ""}${n.last_run ? `, last run ${fmtTime(n.last_run)}` : ""}`;
      out += `<g class="node" tabindex="0" role="listitem" aria-label="${esc(tip)}"><title>${esc(tip)}</title>
        <rect x="${p.x}" y="${p.y}" width="${w}" height="${h}" rx="6" fill="${fill}" stroke="${stroke}" ${st === "never_run" ? 'stroke-dasharray="5 4"' : ""}/>
        <text x="${p.x + 12}" y="${p.y + 26}" font-size="15" font-weight="700" fill="#1C2A44">${i + 1}. ${esc(id)}</text>
        <text x="${p.x + 12}" y="${p.y + 47}" font-size="11.5" fill="#5A6880">${esc(sub)}</text></g>`;
    });
    out += `<text x="10" y="160" font-size="12" fill="#5A6880">Solid arrows: main flow. Dashed arrows: a stage also reads an earlier stage's output.</text>`;
    svg.innerHTML = out;
  }

  function topoOrder(dag) {
    const indeg = {}, adj = {};
    dag.nodes.forEach((n) => { indeg[n.id] = 0; adj[n.id] = []; });
    dag.edges.forEach((e) => { if (adj[e.from]) { adj[e.from].push(e.to); indeg[e.to]++; } });
    const original = dag.nodes.map((n) => n.id);
    const q = original.filter((id) => indeg[id] === 0), out = [];
    while (q.length) {
      q.sort((a, b) => original.indexOf(a) - original.indexOf(b));
      const id = q.shift(); out.push(id);
      adj[id].forEach((t) => { if (--indeg[t] === 0) q.push(t); });
    }
    return out.length === original.length ? out : original;
  }

  function renderRuns(data) {
    const tbody = $("#runs-table tbody");
    if (!data.runs.length) { tbody.innerHTML = `<tr><td colspan="5" class="muted">No runs yet. Click “Run pipeline” to start the first one.</td></tr>`; return; }
    tbody.innerHTML = data.runs.map((r) => {
      const stages = (r.stages || []).map((s) =>
        `<li${s.error ? ' class="err"' : ""}><span>${esc(s.stage)}</span> ${s.status === "success" ? "✓" : "✗"} ${fmtDur(s.duration_s)}${s.error ? `: ${esc(s.error.slice(0, 160))}` : ""}</li>`).join("");
      const trig = { manual: "Manual", drift_alert: "Drift alert", cli: "Terminal" }[r.trigger] || r.trigger;
      return `<tr><td>${esc(fmtTime(r.started_at))}</td>
        <td>${esc(trig)}<div class="muted" style="font-size:13px">${esc(r.reason || "")}${r.data_version ? ` (data ${esc(r.data_version)})` : ""}</div></td>
        <td><span class="badge ${esc(r.status)}">${esc(r.status)}</span>${stages ? `<ul class="stage-list">${stages}</ul>` : ""}</td>
        <td>${fmtDur(r.duration_s)}</td>
        <td>${r.trigger !== "cli" ? `<button class="btn small secondary" data-log="${esc(r.run_id)}">Log</button>` : ""}</td></tr>`;
    }).join("");
    tbody.querySelectorAll("[data-log]").forEach((b) => b.addEventListener("click", () => showLog(b.dataset.log)));
  }

  async function showLog(runId) {
    try {
      const data = await api("pipeline", `api/v1/pipeline/runs/${encodeURIComponent(runId)}/log`);
      await confirmDialog(`Console output of run ${runId}`, `<pre>${esc(data.lines.join("\n"))}</pre>`);
    } catch (e) { toast(e.message); }
  }

  function renderReports(rep) {
    const dq = rep.data_quality || {}, fe = rep.featurize_summary || {}, m = rep.metrics || {}, dr = rep.drift_report || {}, sp = rep.split_summary || {};
    const rows = [
      ["Plots ingested", dq.rows_in?.toLocaleString()],
      ["Plots kept after cleaning", dq.rows_out?.toLocaleString()],
      ["Ray preprocessing throughput", dq.throughput_rows_per_s ? `${Math.round(dq.throughput_rows_per_s).toLocaleString()} rows/s` : null],
      ["TF-IDF transform throughput", fe.transform_throughput_rows_per_s ? `${Math.round(fe.transform_throughput_rows_per_s).toLocaleString()} rows/s` : null],
      ["Training rows (data " + (sp.data_version || "?") + ")", sp.rows_train?.toLocaleString()],
      ["Best model", m.best_model],
      ["Test micro-F1 / macro-F1", m.test_micro_f1 != null ? `${m.test_micro_f1.toFixed(3)} / ${m.test_macro_f1.toFixed(3)}` : null],
      ["Latency p95 (single plot)", m.latency_p95_ms != null ? `${m.latency_p95_ms.toFixed(1)} ms` : null],
      ["Acceptance criteria", m.acceptance_passed == null ? null : m.acceptance_passed ? "Passed" : "Not met"],
      ["Deployment decision", m.promotion_reason],
      ["Drift vs newer films", dr.drift_score != null ? `${dr.drift_score.toFixed(2)} (limit ${dr.threshold})` : null],
    ];
    $("#report-list").innerHTML = rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v ?? "–")}</dd></div>`).join("");
  }

  async function loadPipeline() {
    const errBox = $("#pipeline-error");
    try {
      const [status, dag, runs, reports] = await Promise.all([
        api("pipeline", "api/v1/pipeline/status"), api("pipeline", "api/v1/pipeline/dag"),
        api("pipeline", "api/v1/pipeline/runs?limit=15"), api("pipeline", "api/v1/pipeline/reports"),
      ]);
      errBox.hidden = true;
      const running = status.state === "running";
      $("#st-state").textContent = running ? "Running…" : "Idle";
      $("#st-state").className = "stat-v" + (running ? "" : status.last_run && status.last_run.status === "failed" ? " bad" : " good");
      $("#st-data").textContent = status.data_version === "v2" ? "v2 (all films)" : status.data_version === "v1" ? "v1 (pre-2000)" : status.data_version;
      $("#st-runs").textContent = `${status.totals.success} / ${status.totals.failed}`;
      const dr = reports.drift_report;
      $("#st-drift").textContent = dr ? dr.drift_score.toFixed(2) : "–";
      $("#st-drift").className = "stat-v" + (dr ? (dr.retrain_recommended ? " bad" : " good") : "");
      $("#run-btn").disabled = running; $("#retrain-btn").disabled = running;
      renderDag(dag, null);
      renderRuns(runs);
      renderReports(reports);
    } catch (e) {
      errBox.hidden = false; errBox.textContent = e.message;
      telemetry({ type: "ui_error", name: e.code || "pipeline_load", detail: e.message });
    }
    try {
      const model = await api("gateway", "api/v1/model");
      $("#st-model").innerHTML = model.version
        ? (model.mlflow_run_url ? `<a href="${esc(model.mlflow_run_url)}" target="_blank" rel="noopener">v${esc(model.version)} ${esc(model.algorithm || "")}</a>` : `v${esc(model.version)}`)
        : "none yet";
      const f1 = model.metrics && model.metrics.test_micro_f1;
      $("#st-f1").textContent = f1 != null ? f1.toFixed(3) : "–";
    } catch (_) { $("#st-model").textContent = "unavailable"; }
  }

  async function trigger(body, title, text) {
    const ok = await confirmDialog(title, `<p>${text}</p>`, "Start run");
    if (!ok) return;
    try {
      const run = await api("pipeline", "api/v1/pipeline/trigger", { method: "POST", body });
      telemetry({ type: "action", name: body.data_version ? "retrain" : "run_pipeline" });
      toast(`Run ${run.run_id} started`);
      loadPipeline();
    } catch (e) { toast(e.message); telemetry({ type: "ui_error", name: e.code || "trigger", detail: e.message }); }
  }
  $("#run-btn").addEventListener("click", () => trigger({ reason: "manual run from UI" }, "Run the pipeline?",
    "Only the steps whose code, data or settings changed will run. This can take a few minutes."));
  $("#retrain-btn").addEventListener("click", () => trigger({ reason: "retrain with newer films (UI)", data_version: "v2" },
    "Retrain with newer films?", "The training data will include films released after 2000 (data version 2). The new model goes live only if it passes the quality checks."));

  function renderStaticPipelineBits() {
    const g = CFG.grafanaUrl, uid = CFG.grafanaDashboardUid;
    $("#grafana-link").href = `${g}/d/${uid}`;
    const panels = $("#grafana-panels");
    // Only embed the panels when Grafana answers; otherwise explain how to start it.
    fetch(`${g}/api/health`, { mode: "no-cors" }).then(() => {
      panels.innerHTML = GRAFANA_PANELS.map((p) =>
        `<iframe title="${esc(p.title)}" loading="lazy" src="${esc(g)}/d-solo/${esc(uid)}/plotgenre?orgId=1&panelId=${p.id}&refresh=10s&from=now-30m&to=now&theme=light"></iframe>`).join("");
    }).catch(() => {
      panels.innerHTML = `<p class="panel-missing">Grafana is not reachable at ${esc(g)}. Start the monitoring services with <code>docker compose up -d grafana prometheus</code> and reload this page.</p>`;
      telemetry({ type: "ui_error", name: "grafana_unreachable" });
    });
    const tools = [
      ["MLflow", CFG.mlflowUrl, "experiments, runs, model registry"],
      ["Grafana", `${g}/d/${uid}`, "monitoring dashboard"],
      ["Prometheus", CFG.prometheusUrl, "metrics and alert rules"],
      ["Alertmanager", CFG.alertmanagerUrl, "active alerts"],
      ["API docs", CFG.gatewayDocsUrl, "gateway endpoints (OpenAPI)"],
    ];
    $("#tool-links").innerHTML = tools.map(([n, u, d]) => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a><span>${esc(d)}</span></li>`).join("");
  }

  // ------------------------------------------------------------------ boot
  renderStaticPipelineBits();
  onInput();
  route();
  checkService();
  setInterval(checkService, 15000);
})();
