// Vanilla JS frontend for the results_chat app. No build step, no CDN
// dependencies -- everything here is served by the Flask app itself.

const sessionId = (() => {
  const KEY = "results_chat_session_id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(KEY, id);
  }
  return id;
})();

function fmtPct(x) { return (x * 100).toFixed(2) + "%"; }

async function loadMode() {
  const r = await fetch("/api/mode");
  const d = await r.json();
  const el = document.getElementById("mode-banner");
  el.textContent = d.mode === "llm"
    ? `LLM mode (${d.provider} / ${d.model})`
    : "Factual-answer mode (no LLM configured) -- deterministic evidence lookup";
  el.classList.add(d.mode === "llm" ? "llm" : "factual");
  el.title = d.note;
  return d;
}

function renderDashboard(d) {
  const cards = document.getElementById("dashboard-cards");
  const matchOk = d.rtl_vs_native.n_matched === d.rtl_vs_native.n_cases;
  cards.innerHTML = `
    <div class="card">
      <h4>Functional completion</h4>
      <div class="big ${matchOk ? "ok" : "bad"}">${d.completion.run_id}</div>
      <div>${d.completion.checker_verdict}</div>
      <div class="cite">${d.completion.citation}</div>
    </div>
    <div class="card">
      <h4>RTL vs native agreement</h4>
      <div class="big ${matchOk ? "ok" : "bad"}">${d.rtl_vs_native.n_matched}/${d.rtl_vs_native.n_cases}</div>
      <div class="caveat">Exact score+class match; not the same as classifier correctness.</div>
      <div class="cite">${d.rtl_vs_native.citation}</div>
    </div>
    <div class="card">
      <h4>Classifier quality (test split)</h4>
      <div class="big">${fmtPct(d.classifier_quality.test_accuracy)} / F1 ${d.classifier_quality.test_macro_f1.toFixed(5)}</div>
      <div class="caveat">Target macro-F1 &ge; ${d.classifier_quality.quality_target_macro_f1} --
        ${d.classifier_quality.quality_target_met ? "met" : "NOT met"}.
        On these 20 fixed cases: ${d.classifier_quality.n_correct_on_fixed_cases}/${d.classifier_quality.n_fixed_cases} correct.</div>
      <div class="cite">${d.classifier_quality.citation}</div>
    </div>
    <div class="card">
      <h4>Simulation timing</h4>
      <div class="big">${d.timing.final_cycle.toLocaleString()} cycles</div>
      <div>${d.timing.wall_clock_zenith_reported} wall-clock (simulator)</div>
      <div class="caveat">${d.timing.caveat}</div>
      <div class="cite">${d.timing.citation}</div>
    </div>
    <div class="card">
      <h4>Tensor arena memory</h4>
      <div class="big">${d.memory.tensor_arena_measured_peak_bytes} / ${d.memory.tensor_arena_reserved_bytes} bytes</div>
      <div class="caveat">${d.memory.caveat}</div>
      <div class="cite">${d.memory.citation}</div>
    </div>
    <div class="card">
      <h4>Processor verification</h4>
      <div class="big ${d.processor_verification.directed_tests_pass ? "ok" : "bad"}">
        ${d.processor_verification.directed_tests_pass ? "All directed tests pass" : "Failures present"}
      </div>
      <div>${d.processor_verification.random_instruction_mismatches} mismatches (1100-instruction random comparison)</div>
      <div class="cite">${d.processor_verification.citation}</div>
    </div>
  `;

  const tbody = document.getElementById("cases-tbody");
  tbody.innerHTML = d.cases.map(c => `
    <tr class="${c.rtl_matches_native ? "" : "mismatch"} ${c.has_score_tie ? "tie" : ""}">
      <td>${c.case_id}</td>
      <td>${c.sample_id}</td>
      <td>${c.ground_truth_class}</td>
      <td>${c.native_predicted_class} ${JSON.stringify(c.native_scores)}</td>
      <td>${c.rtl_predicted_class} ${JSON.stringify(c.rtl_scores)}</td>
      <td class="${c.rtl_matches_native ? "ok" : "bad"}">${c.rtl_matches_native ? "MATCH" : "MISMATCH"}</td>
      <td class="${c.classifier_correct ? "ok" : "bad"}">${c.classifier_correct ? "yes" : "no"}</td>
      <td>${c.has_score_tie ? "tie: " + c.tie_class_names.join("/") : ""}</td>
      <td>${c.invoke_elapsed_cycles ? c.invoke_elapsed_cycles.toLocaleString() : ""}</td>
    </tr>
  `).join("");
}

async function loadDashboard() {
  const r = await fetch("/api/dashboard");
  if (!r.ok) {
    document.getElementById("dashboard-cards").textContent = "Dashboard unavailable: evidence failed to load.";
    return;
  }
  const d = await r.json();
  renderDashboard(d);
}

async function loadSuggested(lang) {
  const r = await fetch(`/api/suggested_questions?lang=${lang === "es" ? "es" : "en"}`);
  const d = await r.json();
  const box = document.getElementById("suggested");
  box.innerHTML = "";
  d.questions.forEach(q => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.textContent = q;
    chip.addEventListener("click", () => sendMessage(q));
    box.appendChild(chip);
  });
}

function appendMessage(role, text, citations, followups, chart, mode) {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = "msg " + role;

  if (mode) {
    const badge = document.createElement("div");
    badge.className = "mode-tag";
    badge.textContent = mode === "llm" ? "LLM" : "factual";
    div.appendChild(badge);
  }

  const p = document.createElement("div");
  p.textContent = text;
  div.appendChild(p);

  if (chart) {
    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    const img = document.createElement("img");
    img.src = chart.png_url + "?v=" + chart.chart_id;
    img.alt = chart.title;
    img.loading = "lazy";
    wrap.appendChild(img);

    const links = document.createElement("div");
    links.className = "chart-links";
    for (const [label, url] of [["PNG", chart.png_url], ["SVG", chart.svg_url], ["CSV", chart.csv_url]]) {
      const a = document.createElement("a");
      a.href = url;
      a.textContent = "Download " + label;
      a.setAttribute("download", "");
      links.appendChild(a);
    }
    wrap.appendChild(links);
    div.appendChild(wrap);
  }

  if (citations && citations.length) {
    const c = document.createElement("div");
    c.className = "citations";
    c.textContent = "Sources: " + citations.join(" | ");
    div.appendChild(c);
  }
  if (followups && followups.length) {
    const f = document.createElement("div");
    f.className = "followups";
    followups.forEach(q => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.type = "button";
      chip.textContent = q;
      chip.addEventListener("click", () => sendMessage(q));
      f.appendChild(chip);
    });
    div.appendChild(f);
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function sendMessage(text) {
  const langSel = document.getElementById("lang-select").value;
  appendMessage("user", text, [], []);
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      message: text,
      session_id: sessionId,
      lang: langSel === "auto" ? null : langSel,
    }),
  });
  if (!resp.ok) {
    appendMessage("bot", "Error: the chat backend returned an error.", [], []);
    return;
  }
  const d = await resp.json();
  appendMessage("bot", d.answer, d.citations, d.followups, d.chart, d.mode);
  loadSuggested(d.lang);
}

document.getElementById("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});

loadMode();
loadDashboard();
loadSuggested("en");
