/* Job Hunt Copilot front-end. Plain JavaScript, no frameworks, no build step. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const show = (el) => el.removeAttribute("hidden");
  const hide = (el) => el.setAttribute("hidden", "");
  let toastTimer = null;
  function toast(msg, kind) { const t = $("toast"); t.textContent = msg; t.className = "toast" + (kind ? " " + kind : ""); show(t); clearTimeout(toastTimer); toastTimer = setTimeout(() => hide(t), kind === "bad" ? 7000 : 3500); }
  const SERVER_DOWN = "The app's server isn't answering. Go back to the terminal window and start it again with: python app.py";
  async function api(path, opts = {}) {
    let res;
    try { res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts }); }
    catch (e) { if (e.name === "AbortError") throw e; throw new Error(SERVER_DOWN); }
    let data = null; try { data = await res.json(); } catch (_) { /* none */ }
    if (!res.ok) { const msg = (data && (data.detail || data.message)) || `Something went wrong (${res.status}).`; throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg)); }
    return data;
  }
  async function copyText(text) { try { await navigator.clipboard.writeText(text); toast("Copied!", "ok"); } catch (_) { toast("Couldn't copy automatically — select the text and press Ctrl+C.", "bad"); } }
  function download(name, text) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" })); a.download = name; a.click(); URL.revokeObjectURL(a.href); }

  const state = { status: null, app: null, question: null };
  const screens = ["setup", "input", "results"];
  function go(name) { hide($("toast")); screens.forEach((s) => hide($("screen-" + s))); show($("screen-" + name)); window.scrollTo({ top: 0, behavior: "smooth" }); }

  // ---------- status ----------
  async function refreshStatus(probe) {
    try { state.status = await api("/api/status" + (probe ? "?probe=1" : "")); }
    catch (e) { $("engineText").textContent = "Can't reach the app"; $("engineDot").className = "dot bad"; toast(e.message, "bad"); return; }
    const p = state.status.provider;
    const names = { ollama: "AI on my computer", openai: "Cloud AI (OpenAI)", gemini: "Cloud AI (Gemini)", offline: "No AI (checklist)" };
    $("engineText").textContent = names[p.name] + (p.ok ? "" : " — problem");
    $("engineDot").className = "dot " + (p.ok ? (p.name === "offline" ? "warn" : "ok") : "bad");
    $("enginePill").title = p.message;
    $("privacyText").textContent = p.local ? "Your resume never leaves this computer." : "Cloud mode is on: your resume and the posting are sent to the AI company when you click an AI button.";
    const aiOff = p.name === "offline";
    const hint = aiOff ? "No AI selected — you'll get a checklist and a fill-in template instead. Turn on an AI option in Settings for a real rewrite." : (!p.ok ? "The AI option has a problem (see the pill at the top). You'll get the no-AI version until it's fixed." : "");
    $("tailorHint").textContent = hint; $("letterHint").textContent = hint; $("gradeHint").textContent = aiOff ? "No AI: feedback uses simple rules." : "";
    $("tailorBtn").textContent = aiOff ? "Show me what to change" : "Rewrite it for me";
    $("letterBtn").textContent = aiOff ? "Give me a template" : "Write it";
  }

  // ---------- first run ----------
  async function initSetup() {
    const o = state.status.ollama, el = $("ollamaStatus");
    if (o.running && o.models.length) { el.textContent = "✓ Found Ollama with " + o.models[0]; el.className = "choice-status ok"; }
    else if (o.running) { el.textContent = "Ollama is running but has no model yet (we'll show you how)"; el.className = "choice-status"; }
    else { el.textContent = "Not found — we'll show you how to install it (free)"; el.className = "choice-status bad"; }
    document.querySelectorAll(".choice").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const c = btn.dataset.choice;
          const body = c === "ollama" ? { provider: "ollama", model: o.models[0] || "llama3.2:3b" } : c === "cloud" ? { provider: "openai" } : { provider: "offline" };
          await api("/api/settings", { method: "POST", body: JSON.stringify({ ...body, setup_complete: true }) });
          await refreshStatus(); go("input");
          if (c === "cloud") { openSettings(); toast("Paste your API key, click Test, then Save.", ""); }
          else if (c === "ollama" && !(o.running && o.models.length)) { openSettings(); toast("Follow the steps in the box to install Ollama, then click Test.", ""); }
        } catch (e) { toast("Couldn't save that choice: " + e.message, "bad"); }
      };
    });
  }

  // ---------- input ----------
  const dz = $("dropzone"), fileInput = $("fileInput");
  dz.onclick = () => fileInput.click();
  dz.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } };
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => { const f = e.dataTransfer.files && e.dataTransfer.files[0]; if (f) loadResumeFile(f); });
  fileInput.onchange = () => { if (fileInput.files[0]) loadResumeFile(fileInput.files[0]); fileInput.value = ""; };
  async function loadResumeFile(file) {
    const fd = new FormData(); fd.append("file", file);
    dz.querySelector(".drop-title").textContent = "Reading " + file.name + "…";
    try {
      const res = await fetch("/api/resume/file", { method: "POST", body: fd }).catch(() => { throw new Error(SERVER_DOWN); });
      const d = await res.json().catch(() => null);
      if (!res.ok) throw new Error((d && d.detail) || "Could not read that file.");
      $("resumeText").value = d.text; count();
      toast(`Read ${file.name}. Check the text looks right, then paste the job posting.`, "ok");
      if (d.warnings && d.warnings.length) toast(d.warnings[0], "");
    } catch (e) { toast(e.message, "bad"); }
    finally { dz.querySelector(".drop-title").innerHTML = '📄 Drop your resume file here or <span class="link">choose it</span>'; }
  }
  function count() {
    const r = $("resumeText").value.trim().split(/\s+/).filter(Boolean).length, p = $("postingText").value.trim().split(/\s+/).filter(Boolean).length;
    $("resumeCount").textContent = r ? `${r} words` : ""; $("postingCount").textContent = p ? `${p} words` : "";
  }
  $("resumeText").oninput = count; $("postingText").oninput = count;
  $("sampleBtn").onclick = async () => { try { const d = await api("/api/sample"); $("resumeText").value = d.resume; $("postingText").value = d.posting; $("companyName").value = "Northstar Analytics"; count(); toast("Example loaded. Click Compare them.", "ok"); } catch (e) { toast(e.message, "bad"); } };
  $("matchBtn").onclick = async () => {
    const resume = $("resumeText").value, posting = $("postingText").value;
    if (resume.trim().length < 100) { toast("Paste your whole resume first (it looks too short).", "bad"); return; }
    if (posting.trim().length < 80) { toast("Paste the full job posting — the description and the requirements.", "bad"); return; }
    $("matchBtn").disabled = true; $("matchBtn").textContent = "Comparing…";
    try {
      if ($("rememberResume").checked) api("/api/resume/save", { method: "POST", body: JSON.stringify({ text: resume }) }).catch(() => {});
      const d = await api("/api/match", { method: "POST", body: JSON.stringify({ resume, posting, company: $("companyName").value, app_id: state.app && state.app.resume === resume && state.app.posting === posting ? state.app.id : "" }) });
      state.app = { id: d.id, resume, posting, match: d.match, questions: d.questions, title: d.title, company: d.company, status: "draft" };
      renderResults(); go("results"); setPane("fit");
    } catch (e) { toast(e.message, "bad"); }
    finally { $("matchBtn").disabled = false; $("matchBtn").textContent = "Compare them →"; }
  };
  $("backBtn").onclick = () => go("input");
  $("brandLink").onclick = (e) => { e.preventDefault(); if (state.status && state.status.settings.setup_complete) go("input"); };

  // ---------- results ----------
  function setPane(name) {
    document.querySelectorAll(".subtab").forEach((t) => t.classList.toggle("active", t.dataset.pane === name));
    ["fit", "resume", "letter", "interview"].forEach((p) => (p === name ? show($("pane-" + p)) : hide($("pane-" + p))));
  }
  document.querySelectorAll(".subtab").forEach((t) => (t.onclick = () => setPane(t.dataset.pane)));

  function renderResults() {
    const a = state.app, m = a.match;
    $("rTitle").textContent = a.title || "Job"; $("rCompany").textContent = a.company || "";
    $("rStatus").value = a.status || "draft";
    const pct = m.score; const ring = $("scoreRing");
    ring.style.setProperty("--pct", pct); ring.style.setProperty("--ring", pct >= 70 ? "#1e9e5a" : pct >= 45 ? "#d98500" : "#d7373f");
    $("scoreNum").textContent = pct + "%";
    $("scoreWords").textContent = pct >= 70 ? `Strong match. You hit ${m.required_matched} of ${m.required_count} required skills.` : pct >= 45 ? `Decent match. ${m.required_matched} of ${m.required_count} required skills found — the missing ones below are where to focus.` : `Low keyword match (${m.required_matched} of ${m.required_count} required). Either add the missing words where they're true, or this may not be the right posting.`;
    $("rMissing").innerHTML = m.missing.length ? m.missing.map((x) => `<div class="kw"><div class="name">${esc(x.skill)}<span class="req ${x.weight === 2 ? "" : "nice"}">${x.weight === 2 ? "required" : "nice to have"}</span></div><div class="ev">${x.asked && x.asked[0] ? `Posting: <q>${esc(x.asked[0])}</q>` : ""}</div></div>`).join("") : '<p class="empty">Nothing missing — your resume mentions every skill the posting names.</p>';
    $("rMatched").innerHTML = m.matched.length ? m.matched.map((x) => `<div class="kw"><div class="name">✓ ${esc(x.skill)}</div><div class="ev">${x.evidence && x.evidence[0] ? `Your resume: <q>${esc(x.evidence[0])}</q>` : ""}</div></div>`).join("") : '<p class="empty">No overlapping skills found yet.</p>';
    const st = { ok: "✅", gap: "❌", unclear: "❓" };
    $("rReqs").innerHTML = m.requirements.length ? m.requirements.map((r) => `<div class="reqrow"><div class="st">${st[r.status]}</div><div><b>${esc(r.item)}</b>${r.status !== "ok" ? `<div class="muted small">${esc(r.tip)}</div>` : ""}</div></div>`).join("") : '<p class="muted small">The posting didn\'t state years, degree, or certifications.</p>';
    $("rAts").innerHTML = m.ats.map((x) => `<div class="ats ${x.level}"><b>${esc(x.title)}</b>${esc(x.detail)}</div>`).join("");
    // interview
    const qb = (list, cls) => list.map((q, i) => `<button class="qbtn" data-q="${esc(q.q)}" data-why="${esc(q.why)}">${esc(q.q)}</button>`).join("") || '<p class="muted small">None for this posting.</p>';
    $("qRole").innerHTML = qb(a.questions.role); $("qGaps").innerHTML = qb(a.questions.gaps); $("qBehav").innerHTML = qb(a.questions.behavioral);
    document.querySelectorAll(".qbtn").forEach((b) => (b.onclick = () => pickQuestion(b)));
    hide($("tailorOut")); hide($("tailorChecklist")); hide($("letterOut")); hide($("gradeOut"));
    $("answerText").value = ""; $("answerText").disabled = true; $("gradeBtn").disabled = true; $("micBtn").disabled = true; $("practiceQ").textContent = "Pick a question on the left."; $("practiceWhy").textContent = "";
  }
  $("rStatus").onchange = async () => { try { await api(`/api/apps/${state.app.id}/status`, { method: "POST", body: JSON.stringify({ status: $("rStatus").value }) }); state.app.status = $("rStatus").value; toast("Saved.", "ok"); } catch (e) { toast(e.message, "bad"); } };

  // ---------- tailor ----------
  $("tailorBtn").onclick = async () => {
    const forId = state.app.id;
    $("tailorBtn").disabled = true; show($("tailorWorking")); hide($("tailorOut")); hide($("tailorChecklist"));
    const p = state.status.provider; $("tailorWorkingText").textContent = p.name === "ollama" ? "Rewriting… this can take 1–4 minutes with a local AI. You can switch tabs meanwhile." : p.name === "offline" ? "Building your checklist…" : "Rewriting… usually 10–30 seconds.";
    try {
      const d = await api("/api/tailor", { method: "POST", body: JSON.stringify({ app_id: forId }) });
      if (!state.app || state.app.id !== forId) return; // user moved to a different job meanwhile
      if (d.error) toast(d.error, "bad");
      showTailor(d);
    } catch (e) { toast(e.message, "bad"); }
    finally { $("tailorBtn").disabled = false; hide($("tailorWorking")); }
  };
  function showTailor(d) {
    hide($("tailorOut")); hide($("tailorChecklist"));
    if (!d) return;
    if (d.engine === "checklist") {
      $("tailorChecklistItems").innerHTML = (d.checklist || []).map((t) => `<li>${esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</li>`).join("") || "<li>Your resume already covers everything the posting names. Nice.</li>";
      show($("tailorChecklist"));
    } else {
      $("tailorDiff").innerHTML = (d.diff || []).map((l) => `<div class="${l.type}">${esc(l.text) || "&nbsp;"}</div>`).join("");
      $("tailorClean").value = d.resume || "";
      if (d.warnings && d.warnings.length) { $("tailorWarnings").innerHTML = d.warnings.map((w) => `<div>⚠️ ${esc(w)}</div>`).join(""); show($("tailorWarnings")); } else hide($("tailorWarnings"));
      const ch = (d.changes || []).map((c) => `<div>• ${esc(c)}</div>`).join("") + ((d.could_not_address || []).length ? `<div style="margin-top:.4rem"><b>Couldn't address honestly:</b> ${esc(d.could_not_address.join(", "))} — your resume doesn't show these, so nothing was added.</div>` : "");
      if (ch) { $("tailorChanges").innerHTML = ch; show($("tailorChanges")); } else hide($("tailorChanges"));
      setView("diff"); show($("tailorOut"));
    }
  }
  function setView(v) { document.querySelectorAll(".view-toggle .btn").forEach((b) => b.classList.toggle("active", b.dataset.view === v)); v === "diff" ? (show($("tailorDiff")), hide($("tailorClean"))) : (hide($("tailorDiff")), show($("tailorClean"))); }
  document.querySelectorAll(".view-toggle .btn").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
  $("tailorCopy").onclick = () => copyText($("tailorClean").value);
  $("tailorDownload").onclick = () => download("resume-tailored.txt", $("tailorClean").value);
  $("tailorAgain").onclick = () => $("tailorBtn").click();

  // ---------- letter ----------
  $("letterBtn").onclick = async () => {
    const forId = state.app.id;
    $("letterBtn").disabled = true; show($("letterWorking")); hide($("letterOut"));
    try {
      const d = await api("/api/cover-letter", { method: "POST", body: JSON.stringify({ app_id: forId, details: $("letterDetails").value, tone: $("letterTone").value }) });
      if (!state.app || state.app.id !== forId) return;
      if (d.error) toast(d.error, "bad");
      showLetter(d);
    } catch (e) { toast(e.message, "bad"); }
    finally { $("letterBtn").disabled = false; hide($("letterWorking")); }
  };
  function showLetter(d) {
    hide($("letterOut"));
    if (!d || !d.text) return;
    $("letterText").value = d.text;
    $("letterNote").textContent = d.engine === "template" ? "Fill-in template (no AI). Replace every [bracket] with your own words." : "Written by the AI from your resume. Check every fact.";
    if (d.warnings && d.warnings.length) { $("letterWarnings").innerHTML = d.warnings.map((w) => `<div>⚠️ ${esc(w)}</div>`).join(""); show($("letterWarnings")); } else hide($("letterWarnings"));
    show($("letterOut"));
  }
  $("letterCopy").onclick = () => copyText($("letterText").value);
  $("letterDownload").onclick = () => download("cover-letter.txt", $("letterText").value);
  $("letterAgain").onclick = () => $("letterBtn").click();

  // ---------- interview ----------
  function showLastAnswer(answers) {
    if (!answers || !answers.length) return;
    const last = answers[answers.length - 1];
    const btn = Array.from(document.querySelectorAll(".qbtn")).find((b) => b.dataset.q === last.q);
    if (btn) pickQuestion(btn); else { state.question = last.q; $("practiceQ").textContent = last.q; $("practiceWhy").textContent = ""; $("answerText").disabled = false; $("gradeBtn").disabled = false; }
    $("answerText").value = last.a || "";
    if (last.result && typeof last.result.score === "number") renderGrade(last.result);
  }
  function renderGrade(d) {
    $("gradeScore").textContent = "★".repeat(d.score) + "☆".repeat(5 - d.score) + `  ${d.score}/5`;
    $("gradeStrengths").innerHTML = (d.strengths || []).map((s) => `<li>${esc(s)}</li>`).join("") || "<li>—</li>";
    $("gradeImprove").innerHTML = (d.improve || []).map((s) => `<li>${esc(s)}</li>`).join("") || "<li>Nothing big — practice it out loud.</li>";
    $("gradeStar").textContent = d.missing_star && d.missing_star.length ? `Missing from the STAR shape: ${d.missing_star.join(", ")}.` : "You covered Situation, Task, Action and Result.";
    $("gradeOutline").textContent = d.better_answer_outline || "";
    show($("gradeOut"));
  }
  function pickQuestion(btn) {
    document.querySelectorAll(".qbtn").forEach((b) => b.classList.remove("active")); btn.classList.add("active");
    state.question = btn.dataset.q; $("practiceQ").textContent = btn.dataset.q; $("practiceWhy").textContent = btn.dataset.why;
    $("answerText").disabled = false; $("gradeBtn").disabled = false; $("micBtn").disabled = !window.SpeechRecognition && !window.webkitSpeechRecognition; $("answerText").value = ""; hide($("gradeOut")); $("answerText").focus();
    if (window.innerWidth < 900) $("practiceCard").scrollIntoView({ behavior: "smooth" });
  }
  $("gradeBtn").onclick = async () => {
    const ans = $("answerText").value.trim();
    if (!ans) { toast("Type or speak your answer first.", "bad"); return; }
    const forId = state.app.id, forQ = state.question;
    $("gradeBtn").disabled = true; show($("gradeWorking")); hide($("gradeOut"));
    try {
      const d = await api("/api/grade", { method: "POST", body: JSON.stringify({ app_id: forId, question: forQ, answer: ans }) });
      if (!state.app || state.app.id !== forId || state.question !== forQ) return;
      if (d.error) toast(d.error, "bad");
      renderGrade(d);
    } catch (e) { toast(e.message, "bad"); }
    finally { $("gradeBtn").disabled = false; hide($("gradeWorking")); }
  };
  // speech (optional, browser-provided)
  let rec = null;
  $("micBtn").onclick = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast("Your browser doesn't support speech input. Chrome does.", "bad"); return; }
    if (rec) { rec.stop(); return; }
    if (!localStorage.getItem("jh_speech_ok")) {
      if (!confirm("Heads up: speech-to-text is done by your browser, and in Chrome that means your audio is sent to Google's speech service. Typing keeps everything on this computer. Use the microphone anyway?")) return;
      localStorage.setItem("jh_speech_ok", "1");
    }
    rec = new SR(); rec.continuous = true; rec.interimResults = false; rec.lang = navigator.language || "en-US";
    $("micBtn").classList.add("listening"); $("micBtn").textContent = "⏹ Stop";
    rec.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) $("answerText").value += (($("answerText").value ? " " : "") + e.results[i][0].transcript); };
    rec.onend = () => { rec = null; $("micBtn").classList.remove("listening"); $("micBtn").textContent = "🎤 Speak"; };
    rec.onerror = () => { toast("Microphone didn't work. Check your browser's permission, or just type.", "bad"); };
    rec.start();
  };

  // ---------- apps list ----------
  $("appsBtn").onclick = async () => {
    let apps; try { apps = await api("/api/apps"); } catch (e) { toast(e.message, "bad"); return; }
    $("appsList").innerHTML = apps.length ? apps.map((a) => `<div class="app-row"><div><div class="t">${esc(a.title)}<span class="status-chip">${esc(a.status)}</span>${a.unsaved ? '<span class="status-chip" title="Saving is off in Settings; this disappears when the app restarts">not saved</span>' : ""}</div><div class="muted small">${esc(a.company || "")} · ${a.score}% match · ${new Date(a.updated * 1000).toLocaleDateString()}</div></div><div class="row-gap" style="margin:0"><button class="btn small" data-open="${a.id}">Open</button><button class="btn small danger-ghost" data-del="${a.id}">Delete</button></div></div>`).join("") : '<p class="muted">Nothing saved yet.</p>';
    $("appsList").querySelectorAll("[data-open]").forEach((b) => (b.onclick = async () => { const d = await api("/api/apps/" + b.dataset.open); state.app = { id: d.id, resume: d.resume, posting: d.posting, match: d.match, questions: d.questions, title: d.title, company: d.company, status: d.status }; $("resumeText").value = d.resume; $("postingText").value = d.posting; $("companyName").value = d.company || ""; count(); closeModals(); renderResults(); showTailor(d.tailored); showLetter(d.cover_letter); showLastAnswer(d.answers); go("results"); setPane("fit"); const n = (d.tailored ? 1 : 0) + (d.cover_letter ? 1 : 0) + (d.answers && d.answers.length ? 1 : 0); if (n) toast(`Reopened. Your saved ${[d.tailored && "rewrite", d.cover_letter && "cover letter", d.answers && d.answers.length && "practice answer"].filter(Boolean).join(", ")} ${n > 1 ? "are" : "is"} still here.`, "ok"); }));
    $("appsList").querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { if (!confirm("Delete this saved job? This can't be undone.")) return; try { await api("/api/apps/" + b.dataset.del, { method: "DELETE" }); if (state.app && state.app.id === b.dataset.del) { state.app = null; go("input"); } toast("Deleted.", "ok"); } catch (e) { toast(e.message, "bad"); } $("appsBtn").click(); }));
    openModal("modal-apps");
  };
  $("appsNew").onclick = () => { closeModals(); $("postingText").value = ""; $("companyName").value = ""; count(); go("input"); $("postingText").focus(); };
  $("appsDeleteAll").onclick = async () => { if (!confirm("Delete every saved job and your saved resume from this computer?")) return; await api("/api/apps", { method: "DELETE" }); closeModals(); toast("Deleted.", "ok"); $("resumeText").value = ""; count(); };

  // ---------- modals & settings ----------
  function openModal(id) { show($("modalBack")); show($(id)); }
  function closeModals() { hide($("modalBack")); document.querySelectorAll(".modal").forEach(hide); }
  $("modalBack").onclick = closeModals; document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = closeModals));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModals(); });
  $("helpBtn").onclick = () => openModal("modal-help");
  async function openSettings() {
    if (!state.status) { toast("Settings aren't available until the app's server answers.", "bad"); return; }
    await refreshStatus(true);
    const s = state.status.settings, o = state.status.ollama;
    document.querySelector(`input[name=prov][value=${s.provider}]`).checked = true; showProvPanel(s.provider);
    const models = o.models.length ? o.models : [s.provider === "ollama" ? s.model : "llama3.2:3b"];
    $("setOllamaModel").innerHTML = models.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join(""); if (s.provider === "ollama" && models.includes(s.model)) $("setOllamaModel").value = s.model;
    $("setOllamaHost").value = s.ollama_host; $("setOllamaInfo").textContent = o.running ? (o.models.length ? `Found ${o.models.length} model${o.models.length > 1 ? "s" : ""}.` : "Running, but no model downloaded.") : "Ollama is not running.";
    o.running && o.models.length ? hide($("ollamaHelp")) : show($("ollamaHelp"));
    $("setOpenaiKey").value = s.openai_api_key || ""; $("setOpenaiModel").value = s.provider === "openai" ? s.model : ""; $("setOpenaiUrl").value = s.openai_base_url;
    $("setGeminiKey").value = s.gemini_api_key || ""; $("setGeminiModel").value = s.provider === "gemini" ? s.model : "";
    $("setSaveHistory").checked = !!s.save_history; $("setTestOut").textContent = "";
    $("setDataInfo").textContent = `${state.status.apps.length} saved job${state.status.apps.length !== 1 ? "s" : ""}${state.status.saved_resume ? " and your resume" : ""}, stored only in ${state.status.data_dir}`;
    const env = state.status.env_overrides || []; env.length ? (show($("setEnvNote")), $("setEnvNote").textContent = `Note: environment variables (${env.join(", ")}) currently override these settings.`) : hide($("setEnvNote"));
    openModal("modal-settings");
  }
  function showProvPanel(p) { document.querySelectorAll(".prov-panel").forEach((el) => el.classList.toggle("show", el.dataset.prov === p)); }
  document.querySelectorAll("input[name=prov]").forEach((r) => (r.onchange = () => { showProvPanel(r.value); $("setTestOut").textContent = ""; }));
  $("settingsBtn").onclick = openSettings; $("enginePill").onclick = openSettings;
  function collectSettings() {
    const provider = document.querySelector("input[name=prov]:checked").value;
    const body = { provider, ollama_host: $("setOllamaHost").value.trim() || "http://127.0.0.1:11434", openai_base_url: $("setOpenaiUrl").value.trim() || "https://api.openai.com/v1", save_history: $("setSaveHistory").checked };
    if (provider === "ollama") body.model = $("setOllamaModel").value; if (provider === "openai") body.model = $("setOpenaiModel").value.trim(); if (provider === "gemini") body.model = $("setGeminiModel").value.trim(); if (provider === "offline") body.model = "";
    const ok = $("setOpenaiKey").value.trim(); if (ok) body.openai_api_key = ok; const gk = $("setGeminiKey").value.trim(); if (gk) body.gemini_api_key = gk;
    return body;
  }
  $("setTest").onclick = async () => { $("setTestOut").textContent = "Testing…"; $("setTestOut").className = "small"; try { const d = await api("/api/test-connection", { method: "POST", body: JSON.stringify(collectSettings()) }); $("setTestOut").textContent = (d.ok ? "✓ " : "✗ ") + d.message; $("setTestOut").className = "small " + (d.ok ? "status-ok" : "status-bad"); } catch (e) { $("setTestOut").textContent = "✗ " + e.message; $("setTestOut").className = "small status-bad"; } };
  $("setSave").onclick = async () => { try { const d = await api("/api/settings", { method: "POST", body: JSON.stringify({ ...collectSettings(), setup_complete: true }) }); await refreshStatus(); closeModals(); toast(d.provider.ok ? "Saved. " + d.provider.message : "Saved, but: " + d.provider.message, d.provider.ok ? "ok" : "bad"); } catch (e) { toast(e.message, "bad"); } };
  document.querySelectorAll("[data-clear-key]").forEach((b) => (b.onclick = async () => { const f = b.dataset.clearKey; try { await api("/api/settings", { method: "POST", body: JSON.stringify({ [f]: "" }) }); await refreshStatus(); $(f === "openai_api_key" ? "setOpenaiKey" : "setGeminiKey").value = ""; toast("Key removed from this computer.", "ok"); } catch (e) { toast(e.message, "bad"); } }));

  // ---------- boot ----------
  (async function boot() {
    await refreshStatus();
    if (!state.status) { go("input"); toast("The app couldn't load its settings. Try again in a moment, or run: python scripts/selfcheck.py", "bad"); return; }
    if (!state.status.settings.setup_complete) { await refreshStatus(true); await initSetup(); go("setup"); return; }
    try { const r = await api("/api/resume"); if (r.text) { $("resumeText").value = r.text; count(); } } catch (_) { /* fine */ }
    go("input");
  })();
})();
