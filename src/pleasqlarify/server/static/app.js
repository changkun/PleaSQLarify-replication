// Minimal linked-view client for the PleaSQLarify backend (specs 11-14).
let SID = null;

const $ = (id) => document.getElementById(id);
const api = async (path, opts) => (await fetch(path, opts)).json();
const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

$("demo-btn").addEventListener("click", async () => {
  const state = await post("/demo");
  SID = state.session_id;
  render(state);
});

function render(state) {
  $("utterance").value = state.utterance || "";
  $("status").textContent = state.terminated
    ? `converged — ${state.n_candidates} interpretation(s)`
    : `turn ${state.turn} · ${state.n_candidates} candidates`;
  renderActionSpace(state.action_space);
  renderDecisionSpace(state.decision_space);
  renderPredicted(state.predicted_query);
}

function renderActionSpace(as) {
  const svg = $("as-svg");
  svg.innerHTML = "";
  const qs = as.queries;
  if (!qs.length) return;
  const xs = qs.map((q) => q.x), ys = qs.map((q) => q.y);
  const pad = 30, W = 320, H = 300;
  const sx = scale(Math.min(...xs), Math.max(...xs), pad, W - pad);
  const sy = scale(Math.min(...ys), Math.max(...ys), pad, H - pad);
  for (const q of qs) {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    const size = Math.max(8, Math.min(28, 6 + q.rows * 3 + q.cols * 2));
    g.setAttribute("x", sx(q.x) - size / 2);
    g.setAttribute("y", sy(q.y) - size / 2);
    g.setAttribute("width", size);
    g.setAttribute("height", size);
    g.setAttribute("rx", 3);
    g.setAttribute("fill", q.color);
    g.setAttribute("class", "glyph");
    g.setAttribute("title", q.sql);
    g.addEventListener("click", async () => {
      const state = await post(`/session/${SID}/select`, { query_ids: [q.id] });
      render(state);
    });
    const t = document.createElementNS("http://www.w3.org/2000/svg", "title");
    t.textContent = q.sql;
    g.appendChild(t);
    svg.appendChild(g);
  }
}

function scale(lo, hi, a, b) {
  if (hi - lo < 1e-9) return () => (a + b) / 2;
  return (v) => a + ((v - lo) / (hi - lo)) * (b - a);
}

function atomSpan(a, extra) {
  return `<span class="atom ${extra || ""}"><span class="kw">${a.keyword}</span>${
    a.value ? `<span class="val">${a.value}</span>` : ""
  }</span>`;
}

function renderDecisionSpace(ds) {
  const body = $("ds-body");
  if (ds.terminated) {
    body.innerHTML = `<p class="done">Intent identified — no further clarification needed.</p>`;
    return;
  }
  body.innerHTML = "";
  ds.variables.slice(0, 6).forEach((v) => {
    const isTop = v.id === ds.top_id;
    const card = document.createElement("div");
    card.className = "dv-card" + (isTop ? " top" : "");
    const groupAtoms = v.atoms.map((a) => atomSpan(a, "group")).join("");
    let example = "";
    if (v.example) {
      const gset = new Set(v.example.group), iset = new Set(v.example.implicit);
      example =
        `<div class="example">` +
        v.example.atoms
          .map((a) => atomSpan(a, gset.has(a.index) ? "group" : iset.has(a.index) ? "implicit" : ""))
          .join("") +
        `</div>`;
    }
    card.innerHTML =
      `<div>${groupAtoms}</div>${example}` +
      `<div class="dv-actions">` +
      `<button class="yes" data-v="${v.id}" data-a="true">Yes</button>` +
      `<button data-v="${v.id}" data-a="false">No</button>` +
      `<span class="ig">IG ${v.ig.toFixed(3)}</span></div>`;
    body.appendChild(card);
  });
  body.querySelectorAll("button[data-v]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const state = await post(`/session/${SID}/answer`, {
        variable_id: btn.dataset.v,
        value: btn.dataset.a === "true",
      });
      render(state);
    })
  );
}

function renderPredicted(pq) {
  $("pq-body").innerHTML = pq.features
    .map(
      (f) =>
        `<div class="feature-row">${atomSpan(f, f.state)}<span class="prob">${Math.round(
          f.prob * 100
        )}%${f.state === "determined" ? " · determined" : ""}</span></div>`
    )
    .join("");
  const out = pq.output;
  $("po-body").innerHTML = out
    ? `<table><thead><tr>${out.columns.map((c) => `<th>${c}</th>`).join("")}</tr></thead>` +
      `<tbody>${out.rows
        .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
        .join("")}</tbody></table>`
    : "<p class='hint'>No output.</p>";
}
