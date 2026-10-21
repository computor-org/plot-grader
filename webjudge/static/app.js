"use strict";
const CRIT = [
  ["M1", "Gleiche Kurven (keine fehlt, keine zusätzliche)"],
  ["M2", "Gleiche Daten (Form, Lage, Werte)"],
  ["M3", "Gleiche Achsen (linear/log, Bereich)"],
  ["M4", "Achsenbeschriftung (gleiche Größe/Einheit)"],
  ["M5", "Kurven unterscheidbar (Legende passt)"],
  ["M6", "Gleiche Teilbilder"],
];
const $ = (id) => document.getElementById(id);
let S = null;          // {cases, answers, position}
let pos = 0;           // index into S.cases; == length means "done" screen
let pending = 0, commentTimer = null, lbSide = "stu";

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)});
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function status(text, err) {
  const s = $("status"); s.textContent = text; s.className = "status" + (err ? " err" : "");
}

function answerOf(i) {
  return S.answers[S.cases[i].id] || {verdict: null, criteria: [], comment: ""};
}

function nAnswered() {
  return S.cases.filter((c) => (S.answers[c.id] || {}).verdict).length;
}

function firstOpen(from) {
  const n = S.cases.length;
  for (let k = 0; k < n; k++) {
    const i = (from + k) % n;
    if (!answerOf(i).verdict) return i;
  }
  return n;
}

async function save(fields) {
  const c = S.cases[pos];
  const a = Object.assign({}, answerOf(pos), fields);
  S.answers[c.id] = a;
  renderAnswer(); renderProgress();
  pending++; status("Speichere …");
  try {
    const r = await api("/api/answer", {case_id: c.id, verdict: a.verdict,
      criteria: a.criteria, comment: a.comment, position: pos});
    pending--;
    if (!pending) status("Gespeichert " + new Date(r.saved_at).toLocaleTimeString("de-AT"));
  } catch (e) {
    pending--;
    status("Nicht gespeichert – Verbindung prüfen und Seite neu laden", true);
  }
}

function flushComment() {
  if (commentTimer) { clearTimeout(commentTimer); commentTimer = null; }
  if (pos < S.cases.length && $("comment").value !== answerOf(pos).comment) {
    save({comment: $("comment").value});
  }
}

function go(i) {
  flushComment();
  pos = Math.max(0, Math.min(S.cases.length, i));
  api("/api/position", {position: pos}).catch(() => {});
  render();
  window.scrollTo(0, 0);
}

function renderProgress() {
  const n = S.cases.length, done = nAnswered();
  $("bar").style.width = (100 * done / n) + "%";
  $("answered").textContent = done + " beantwortet";
  $("count").textContent = pos < n ? `Fall ${pos + 1} von ${n}` : `${n} Fälle`;
  [...$("dots").children].forEach((d, i) => {
    d.className = (answerOf(i).verdict ? "done" : "") + (i === pos ? " cur" : "");
  });
}

function renderAnswer() {
  const a = answerOf(pos);
  document.querySelectorAll(".verdicts button").forEach((b) =>
    b.classList.toggle("on", b.dataset.v === a.verdict));
  document.querySelectorAll("#crit input").forEach((cb) => {
    cb.checked = a.criteria.includes(cb.value);
  });
}

function render() {
  const n = S.cases.length;
  if (pos >= n) return renderDone();
  $("main").hidden = false;
  const done = document.querySelector(".done-msg"); if (done) done.remove();
  const c = S.cases[pos];
  $("ref").src = "/" + c.ref; $("stu").src = "/" + c.stu;
  $("comment").value = answerOf(pos).comment || "";
  $("prev").disabled = pos === 0;
  renderAnswer(); renderProgress();
  if (pos + 1 < n) {  // preload next pair
    new Image().src = "/" + S.cases[pos + 1].ref; new Image().src = "/" + S.cases[pos + 1].stu;
  }
}

function renderDone() {
  $("main").hidden = true;
  renderProgress();
  let d = document.querySelector(".done-msg");
  if (!d) { d = document.createElement("div"); d.className = "done-msg"; document.body.appendChild(d); }
  const open = S.cases.length - nAnswered();
  d.innerHTML = open === 0
    ? "<h1>Alle Fälle beantwortet – vielen Dank!</h1><p>Die Antworten sind gespeichert. " +
      "Sie können über die Übersicht oben jeden Fall noch einmal öffnen und ändern.</p>"
    : `<h1>Noch ${open} Fälle offen</h1><p><button class="primary" id="gofirst">Zum ersten offenen Fall</button></p>`;
  const b = $("gofirst"); if (b) b.onclick = () => go(firstOpen(0));
}

function toggleCrit(code) {
  const a = answerOf(pos), set = new Set(a.criteria);
  set.has(code) ? set.delete(code) : set.add(code);
  const fields = {criteria: [...set].sort()};
  if (set.size && a.verdict === "PASS") fields.verdict = "FAIL";
  save(fields);
}

function setVerdict(v) {
  const fields = {verdict: v};
  if (v === "PASS") fields.criteria = [];
  save(fields);
}

function openLb(side) {
  lbSide = side; $("lb").classList.add("open"); $("lb").classList.remove("full"); showLb();
}
function showLb() {
  const c = S.cases[pos];
  $("lbimg").src = "/" + (lbSide === "ref" ? c.ref : c.stu);
  $("lbtitle").textContent = lbSide === "ref" ? "Referenz" : "Abgabe";
}
function closeLb() { $("lb").classList.remove("open"); }

function setup() {
  CRIT.forEach(([code, text], k) => {
    const l = document.createElement("label");
    l.innerHTML = `<input type="checkbox" value="${code}"><b>${code}</b><span>${text}</span>`;
    l.title = "Taste " + (k + 1);
    l.querySelector("input").onchange = () => toggleCrit(code);
    $("crit").appendChild(l);
  });
  S.cases.forEach((c, i) => {
    const d = document.createElement("button");
    d.title = "Fall " + (i + 1); d.onclick = () => go(i);
    $("dots").appendChild(d);
  });
  document.querySelectorAll(".verdicts button").forEach((b) => {
    b.onclick = () => setVerdict(b.dataset.v);
  });
  $("prev").onclick = () => go(pos - 1);
  $("next").onclick = () => go(pos + 1);
  $("open").onclick = () => go(firstOpen(pos + 1));
  $("ref").onclick = () => openLb("ref");
  $("stu").onclick = () => openLb("stu");
  $("lbswap").onclick = () => { lbSide = lbSide === "ref" ? "stu" : "ref"; showLb(); };
  $("lbclose").onclick = closeLb;
  $("lbimg").onclick = () => $("lb").classList.toggle("full");
  $("comment").oninput = () => {
    clearTimeout(commentTimer); commentTimer = setTimeout(flushComment, 800);
  };
  $("comment").onblur = flushComment;
  window.addEventListener("beforeunload", flushComment);
  document.addEventListener("keydown", onKey);
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.tagName === "TEXTAREA") {
    if (e.key === "Escape") e.target.blur();
    return;
  }
  const lb = $("lb").classList.contains("open");
  if (lb && e.key === "Escape") return closeLb();
  if (lb && e.key === " ") { e.preventDefault(); return $("lbswap").click(); }
  if (e.key === "ArrowLeft") { closeLb(); return go(pos - 1); }
  if (e.key === "ArrowRight") { closeLb(); return go(pos + 1); }
  if (pos >= S.cases.length) return;
  const k = e.key.toLowerCase();
  if (k === "a") return setVerdict("PASS");
  if (k === "n") return setVerdict("FAIL");
  if (k === "u") return setVerdict("UNSURE");
  if (k >= "1" && k <= "6") return toggleCrit(CRIT[+k - 1][0]);
}

(async function init() {
  try {
    S = await api("/api/state");
  } catch (e) {
    document.body.innerHTML = "<p style='padding:20px'>Kein Zugang. Bitte den persönlichen Link verwenden.</p>";
    return;
  }
  setup();
  pos = S.position === null ? firstOpen(0) : Math.min(S.position, S.cases.length);
  render();
})();
