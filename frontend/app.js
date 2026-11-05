const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  samples: [], pos: [], runs: [], selected: null, file: null, latest: null,
  filter: "", search: "", tolerance: 2, historyRequest: 0, commandIndex: 0, currentPdfUrl: null,
  queue: [], queueIndex: 0, currentQueueCase: null,
};

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;",
}[char]));
const money = (amount, currency) => {
  if (amount == null) return "Not found";
  return currency
    ? new Intl.NumberFormat(undefined, {style:"currency", currency, maximumFractionDigits:2}).format(amount)
    : new Intl.NumberFormat(undefined, {maximumFractionDigits:2}).format(amount);
};
const outcome = decision => decision === "APPROVE"
  ? ["Ready for hand-off", "approve", "✓"]
  : decision === "REJECT" ? ["Stopped for a reason", "reject", "↗"] : ["In review", "review", "◷"];
const outcomeClass = decision => decision === "APPROVE" ? "tag-approve" : decision === "REJECT" ? "tag-reject" : "tag-review";
const commands = [
  {icon:"◫", title:"Go to Review desk", detail:"Start or continue an invoice review", keywords:"home review invoice desk", run:() => setView("desk")},
  {icon:"▤", title:"Open Exception Queue", detail:"Assign, annotate, and resolve cases", keywords:"queue exceptions workbench owner", run:() => setView("queue")},
  {icon:"↗", title:"Open Case history", detail:"Search prior recommendations and evidence", keywords:"history archive records cases", run:() => setView("history")},
  {icon:"▥", title:"Open Analytics", detail:"Review activity and outcome totals", keywords:"analytics charts volume outcomes", run:() => setView("analytics")},
  {icon:"⌘", title:"Read How it works", detail:"See the review rules and boundaries", keywords:"policy rules how model works", run:() => setView("policy")},
  {icon:"▤", title:"View purchasing register", detail:"Inspect the synthetic PO commitments", keywords:"purchase order po register", run:() => { setView("desk"); $("#modalBackdrop").hidden = false; }},
  {icon:"✳", title:"Select clean-match scenario", detail:"Load the prepared exact-match invoice", keywords:"demo happy path sample approve", run:() => { setView("desk"); setSelected("happy_path.pdf"); }},
  {icon:"↑", title:"Choose a PDF to upload", detail:"Open the invoice file picker", keywords:"upload browse document file", run:() => { setView("desk"); $("#invoiceFile").click(); }},
];

async function getJson(url) {
  let response;
  try { response = await fetch(url, {headers:{Accept:"application/json"}}); }
  catch { throw new Error(`Can't reach ${url}. Check that the Mosaic server is running, then retry.`); }
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`The Mosaic server returned an unreadable response for ${url}.`); }
  if (!response.ok) throw new Error(data.error || "Mosaic could not complete that request.");
  return data;
}
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2800);
}
function setSelected(file) {
  state.selected = file;
  state.file = null;
  $("#invoiceFile").value = "";
  $("#filePill").hidden = true;
  $("#uploadTitle").textContent = "Upload a PDF";
  $("#uploadHelp").textContent = "Text-readable · 15 MB max";
  renderScenarios();
  refreshRunButton();
}
function renderScenarios() {
  const list = $("#scenarioList");
  if (!state.samples.length) {
    list.innerHTML = "<div class='recent-empty'>No sample invoices found in data/invoices yet.</div>";
    return;
  }
  const activeSample = state.samples.find(sample => sample.file === state.selected);
  $("#sampleCount").textContent = activeSample?.title || `${state.samples.length} examples`;
  list.innerHTML = state.samples.map(sample => `
    <button class="scenario-option ${state.selected === sample.file ? "selected" : ""}"
      role="option" aria-selected="${state.selected === sample.file}" data-file="${escapeHtml(sample.file)}">
      <span class="scenario-visual">PDF</span>
      <span class="scenario-meta"><b>${escapeHtml(sample.title)}</b><small>${escapeHtml(sample.note)}</small></span>
      <span class="scenario-status status-${escapeHtml(sample.kind)}"></span><span class="select-mark">✓</span>
    </button>`).join("");
  $$(".scenario-option", list).forEach(button => button.addEventListener("click", () => setSelected(button.dataset.file)));
}
function refreshRunButton() {
  const button = $("#runButton");
  button.disabled = !(state.selected || state.file) || button.classList.contains("running");
  button.querySelector("span:nth-child(2)").textContent = state.file
    ? `Review “${state.file.name}”`
    : "Review invoice";
}
function setView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-item").forEach(button => {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const labels = {desk:"Review desk", queue:"Review queue", history:"Case history", analytics:"Analytics", policy:"How it works"};
  $("#crumbTitle").textContent = labels[name] || "Review desk";
  if (name === "history") loadRuns().catch(error => toast(error.message));
  if (name === "queue") loadQueue().catch(error => toast(error.message));
  if (name === "analytics") getJson("/api/summary").then(renderSummary).catch(error => toast(error.message));
  if (name === "policy") renderPolicyCases();
  window.scrollTo({top:0, behavior:"smooth"});
}
function renderInsights(summary) {
  const rows = summary.daily || [];
  const max = Math.max(1, ...rows.map(day => day.total));
  const total = rows.reduce((sum, day) => sum + day.total, 0);
  $("#activityTotal").textContent = `${total} case${total === 1 ? "" : "s"} in this window`;
  $("#activityChart").innerHTML = rows.map(day => {
    const date = new Date(`${day.date}T12:00:00Z`);
    const label = new Intl.DateTimeFormat(undefined, {weekday:"short", timeZone:"UTC"}).format(date);
    const totalHeight = Math.max(2, Math.round(day.total / max * 55));
    const bars = [
      ["approve", day.approved, "Ready for hand-off"],
      ["review", day.review, "Needs a second look"],
      ["reject", day.rejected, "Stopped for a reason"],
    ];
    return `<div class="activity-day ${day.total ? "has-activity" : ""}" title="${escapeHtml(day.date)} · ${day.total} case${day.total === 1 ? "" : "s"}">
      <div class="activity-bars">${bars.map(([kind, count, name]) => {
        const height = count ? Math.max(3, Math.round(totalHeight * count / day.total)) : 0;
        return `<i class="activity-bar ${kind}" style="height:${height}px" title="${escapeHtml(name)}: ${count}"></i>`;
      }).join("")}</div><small>${escapeHtml(label)}</small></div>`;
  }).join("");
  const totalCount = Number(summary.total || 0);
  const approved = Number(summary.approved || 0), review = Number(summary.review || 0), rejected = Number(summary.rejected || 0);
  const readyEnd = totalCount ? approved / totalCount * 100 : 0;
  const reviewEnd = totalCount ? readyEnd + review / totalCount * 100 : readyEnd;
  const bg = totalCount
    ? `conic-gradient(#79ad8b 0 ${readyEnd}%,#dfb563 ${readyEnd}% ${reviewEnd}%,#ce8170 ${reviewEnd}% 100%)`
    : "conic-gradient(#edf0e9 0 100%)";
  $("#outcomeDonut").style.background = bg;
  $("#donutTotal").textContent = totalCount;
  $("#mixTotal").textContent = `${totalCount} TOTAL`;
  $("#mixApproved").textContent = approved;
  $("#mixReview").textContent = review;
  $("#mixRejected").textContent = rejected;
}
function renderSummary(summary) {
  $("#statTotal").textContent = summary.total;
  $("#statApproved").textContent = summary.approved;
  $("#statReview").textContent = summary.review;
  $("#statRejected").textContent = summary.rejected;
  $("#statFeedback").textContent = summary.feedback ?? 0;
  $("#statOverrides").textContent = summary.overrides ?? 0;
  $("#navOpen").textContent = summary.review;
  $("#navOpen").hidden = !summary.review;
  $("#navQueue").textContent = summary.open_cases ?? 0;
  $("#navQueue").hidden = !summary.open_cases;
  const recent = summary.recent || [];
  $("#recentList").innerHTML = recent.length ? recent.map(run => {
    const invoice = run.invoice, decision = run.result.decision;
    const caseCode = `AP-${String(run.id).padStart(6, "0")}`;
    return `<button class="recent-row" data-run-id="${run.id}" aria-label="Open case ${caseCode}, ${escapeHtml(invoice.vendor || "supplier unknown")}">
      <span class="recent-case">${caseCode}</span><span class="recent-supplier">${escapeHtml(invoice.vendor || "Supplier not identified")}</span><span class="recent-invoice">${escapeHtml(invoice.invoice_number || "Reference missing")}</span><span class="recent-amount">${escapeHtml(money(invoice.total, invoice.currency))}</span><span class="outcome-tag ${outcomeClass(decision)}">${outcome(decision)[0]}</span><span class="recent-updated">${escapeHtml(formatDate(run.created_at))} <i>↗</i></span></button>`;
  }).join("") : "<div class='recent-empty'>Your reviewed cases will appear here.</div>";
  $$(".recent-row[data-run-id]").forEach(button => button.addEventListener("click", async () => {
    setView("history");
    try { await loadRuns(); openArchiveCase(Number(button.dataset.runId)); }
    catch (error) { toast(error.message); }
  }));
  renderInsights(summary);
}
function evidenceForCheck(check, invoice, po, allowPdfJump = false) {
  const fields = {
    "Invoice number":[["Invoice number",invoice.invoice_number]],
    "Invoice date":[["Invoice date",invoice.invoice_date]],
    "Supplier identity":[["Supplier",invoice.vendor]],
    "PO reference":[["PO reference",invoice.po_number]],
    "Invoice total":[["Invoice total",invoice.total == null ? null : money(invoice.total,invoice.currency)]],
    "Duplicate screen":[["Invoice number",invoice.invoice_number],["Supplier",invoice.vendor]],
    "Subtotal + tax":[["Subtotal",invoice.subtotal],["Tax",invoice.tax],["Total",invoice.total]],
    "Supplier ↔ PO":[["Invoice supplier",invoice.vendor],["PO supplier",po?.vendor]],
    "PO status":[["PO status",po?.status]],
    "Currency":[["Invoice currency",invoice.currency],["PO currency",po?.currency]],
    "PO balance":[["Invoice amount",invoice.total == null ? null : money(invoice.total,invoice.currency)],["PO commitment",po?.approved_amount == null ? null : money(po.approved_amount,po.currency)]],
  }[check.name] || [];
  const pages = (invoice.raw_text || "").split("\f").map(page=>page.split(/\r?\n/).map(line=>line.trim()).filter(Boolean));
  const normalizeEvidence = value => String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g,"");
  const source = fields.map(([label,value]) => {
    const needle = value == null ? "" : String(value);
    const normalizedNeedle=normalizeEvidence(needle);
    let match=null;
    if (normalizedNeedle) for (let pageIndex=0;pageIndex<pages.length;pageIndex++) {
      const line=pages[pageIndex].find(item=>normalizeEvidence(item).includes(normalizedNeedle));
      if (line) { match={line,page:pageIndex+1}; break; }
    }
    const excerpt=match ? `<small>${allowPdfJump && state.currentPdfUrl ? `<button class="evidence-jump" data-evidence-page="${match.page}">PDF · page ${match.page}</button> ` : `PDF · page ${match.page} · `}Source: “${escapeHtml(match.line)}”</small>` : `<small>${po && label.startsWith("PO") ? "Purchase order register" : "No matching selectable text line"}</small>`;
    return `<div class="evidence-line"><b>${escapeHtml(label)}</b><span>${escapeHtml(value == null ? "Not extracted" : value)}</span>${excerpt}</div>`;
  }).join("");
  return source ? `<details class="check-evidence"><summary>View evidence</summary>${source}</details>` : "";
}
function renderEvidence(data) {
  const invoice = data.invoice || {}, result = data.result || {}, po = result.matched_po;
  const checks = result.checks || [];
  const amount = money(invoice.total, invoice.currency);
  const decision = outcome(result.decision);
  const caseCode = `AP-${String(data.id).padStart(6, "0")}`;
  const field = (label, value) => `<div class="invoice-field"><small>${escapeHtml(label)}</small><b>${escapeHtml(value || "Not found")}</b></div>`;
  const checkRows = checks.length ? checks.map(check => {
    const statusText = check.status === "pass" ? "Clear" : check.status === "fail" ? "Mismatch" : "Check";
    const glyph = check.status === "pass" ? "✓" : check.status === "fail" ? "!" : "·";
    return `<div class="review-check ${escapeHtml(check.status)}"><span class="check-mark">${glyph}</span><div class="check-copy"><b>${escapeHtml(check.name)}</b><small>${escapeHtml(check.detail)}</small>${evidenceForCheck(check,invoice,po,true)}</div><span class="check-status">${statusText}</span></div>`;
  }).join("") : `<div class="review-check review"><span class="check-mark">·</span><div class="check-copy"><b>No checks returned</b><small>Open the case packet for the complete result.</small></div></div>`;
  const poBlock = po
    ? `<div class="po-sheet"><div class="po-sheet-brand">${escapeHtml(po.vendor || "Supplier not identified")}</div><div class="po-sheet-type">PURCHASE ORDER</div><div class="po-number">${escapeHtml(po.po_number || invoice.po_number || "PO not found")}</div><div class="po-facts"><div><small>Status</small><b>${escapeHtml(po.status || "Not found")}</b></div><div><small>Currency</small><b>${escapeHtml(po.currency || "Not stated")}</b></div><div><small>Approved amount</small><b>${escapeHtml(money(po.approved_amount, po.currency))}</b></div></div>${invoice.total != null && po.approved_amount ? `<div class="po-compare"><div><span>Invoice amount</span><b>${escapeHtml(amount)}</b></div><div class="po-meter"><i style="width:${Math.min(100, Math.max(2, invoice.total / po.approved_amount * 100))}%"></i></div><div><span>PO commitment</span><b>${escapeHtml(money(po.approved_amount, po.currency))}</b></div></div>` : ""}<span class="po-status-stamp ${escapeHtml(String(po.status || "").toLowerCase())}">${escapeHtml(po.status || "PO status unavailable")}</span></div>`
    : `<div class="po-sheet po-missing"><div class="po-sheet-type">PURCHASE ORDER</div><div class="po-number">${escapeHtml(invoice.po_number || "No PO reference")}</div><p>No confirmed purchase order is linked to this invoice yet.</p><div class="po-facts"><div><small>Register match</small><b>Not confirmed</b></div><div><small>Next step</small><b>Check the PO register</b></div></div></div>`;
  const candidates = (result.candidates || []).length ? `<div class="candidate-box"><b>Possible register matches · confirm manually</b>${result.candidates.slice(0, 2).map(candidate => `<div><span>${escapeHtml(candidate.po_number)} · ${escapeHtml(candidate.vendor)}</span><small>${Math.round(candidate.score * 100)}% relative fit</small></div>`).join("")}</div>` : "";
  const rawText = invoice.raw_text || "No selectable source text was found.";
  const pdfUrl = state.currentPdfUrl;
  const invoiceFields = [
    ["Invoice date", invoice.invoice_date], ["PO reference", invoice.po_number],
    ["Currency", invoice.currency], ["Subtotal", invoice.subtotal == null ? null : money(invoice.subtotal, invoice.currency)],
    ["Tax", invoice.tax == null ? null : money(invoice.tax, invoice.currency)],
  ];

  $("#caseRef").textContent = caseCode;
  $("#caseState").textContent = decision[0];
  $("#caseState").className = `case-state ${decision[1]}`;
  $("#metaCase").textContent = caseCode;
  $("#metaSupplier").textContent = invoice.vendor || "Supplier not identified";
  $("#metaInvoice").textContent = invoice.invoice_number || "Not found";
  $("#metaPO").textContent = invoice.po_number || po?.po_number || "Not found";
  $("#metaAmount").textContent = amount;
  $("#quickInvoice").textContent = invoice.invoice_number || "Not found";
  $("#quickAmount").textContent = amount;
  $("#quickDate").textContent = invoice.invoice_date || "Not found";

  $("#evidenceCanvas").classList.add("has-result");
  $("#evidenceCanvas").innerHTML = `<div class="evidence-layout">
    <section class="review-column invoice-column"><div class="review-column-head"><span class="column-icon">▤</span><div><b>Invoice</b><small>Original PDF · source document</small></div></div>${pdfUrl ? `<div class="invoice-preview"><iframe class="invoice-iframe" title="Original invoice PDF" src="${escapeHtml(pdfUrl)}#toolbar=1&navpanes=0&view=FitH"></iframe></div><a class="pdf-open-link" href="${escapeHtml(pdfUrl)}" target="_blank" rel="noreferrer">Open original PDF <span>↗</span></a>` : `<div class="invoice-unavailable">Original PDF preview is not available for this saved case.</div>`}<details class="extracted-details"><summary>Extracted invoice details</summary><div class="invoice-ref-row"><span>Invoice number</span><b>${escapeHtml(invoice.invoice_number || "Not found")}</b></div><div class="invoice-fields">${invoiceFields.map(([label, value]) => field(label, value == null ? "Not found" : value)).join("")}</div><div class="invoice-total"><span>Invoice total</span><b>${escapeHtml(amount)}</b></div></details><details class="source-details"><summary>View extracted source text</summary><pre>${escapeHtml(rawText)}</pre></details></section>
    <section class="review-column po-column"><div class="review-column-head"><span class="column-icon">▣</span><div><b>Purchase order</b><small>${po ? "From the connected register" : "Reference needs confirmation"}</small></div></div>${poBlock}${candidates}</section>
    <section class="review-column checks-column"><div class="review-column-head"><span class="column-icon shield-icon">✓</span><div><b>Review checks</b><small>Each check has a reason</small></div></div><div class="review-check-list">${checkRows}</div><div class="decision-result ${decision[1]}"><div class="decision-icon">${decision[2]}</div><div><b>${escapeHtml(decision[0])}</b><p>${escapeHtml(result.reason || "Review the individual checks above.")}</p></div></div><div class="human-note"><span>○</span><p>${escapeHtml(result.next_step || "A person owns the final hand-off.")}</p></div><div class="case-actions"><button class="packet-button" id="downloadPacket">▱ &nbsp; Open case packet</button><button class="history-action" id="viewCaseHistory">View case history <span>→</span></button></div></section>
  </div>`;
  $("#downloadPacket").addEventListener("click", () => downloadJson(data, `mosaic-case-${data.id}.json`));
  $("#viewCaseHistory").addEventListener("click", () => setView("history"));
  $$(".evidence-jump").forEach(button=>button.addEventListener("click", event=>{
    event.preventDefault();
    const iframe=$(".invoice-iframe",$("#evidenceCanvas"));
    if (iframe) { iframe.src=`${pdfUrl}#page=${button.dataset.evidencePage}&toolbar=1&navpanes=0&view=FitH`; iframe.scrollIntoView({behavior:"smooth",block:"center"}); }
  }));
}
function renderLoading() {
  $("#caseRef").textContent = "REVIEW IN PROGRESS";
  $("#caseState").textContent = "Checking invoice";
  $("#caseState").className = "case-state review";
  $("#evidenceCanvas").classList.remove("has-result");
  $("#evidenceCanvas").innerHTML = `<div class="processing"><div class="processing-mark"><span></span><i>✳</i></div><b>Checking the invoice details</b><small>This usually takes a moment.</small><div class="processing-steps">${[
    "Fingerprint the document", "Read the invoice details", "Connect supplier and PO", "Check the math and history",
  ].map((step, index) => `<div class="processing-step" data-step="${index}"><span class="process-indicator">${String(index + 1).padStart(2, "0")}</span>${step}</div>`).join("")}</div></div>`;
}
async function runReview() {
  const button = $("#runButton");
  button.disabled = true;
  button.classList.add("running");
  const label = button.querySelector("span:nth-child(2)").textContent;
  const previousPdfUrl = state.currentPdfUrl;
  state.currentPdfUrl = state.file
    ? URL.createObjectURL(state.file)
    : `/api/sample/${encodeURIComponent(state.selected || "")}`;
  button.querySelector("span:nth-child(2)").textContent = "Checking the details…";
  renderLoading();
  const steps = $$(".processing-step");
  try {
    for (let index = 0; index < steps.length; index++) {
      await new Promise(resolve => setTimeout(resolve, 230));
      steps[index].classList.add("done");
      steps[index].querySelector(".process-indicator").textContent = "✓";
      if (steps[index + 1]) steps[index + 1].classList.add("current");
    }
    const tolerance = encodeURIComponent(state.tolerance);
    const response = state.file
      ? await (() => { const form = new FormData(); form.append("invoice", state.file); return fetch(`/api/upload?tolerance=${tolerance}`, {method:"POST", body:form}); })()
      : await fetch(`/api/review?sample=${encodeURIComponent(state.selected)}&tolerance=${tolerance}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Review failed.");
    state.latest = payload;
    renderEvidence(payload);
    renderSummary(await getJson("/api/summary"));
    await loadRuns();
    await loadQueue().catch(error => toast(error.message));
    toast(`Case #${payload.id} is ready. Your review packet is saved.`);
  } catch (error) {
    $("#evidenceCanvas").innerHTML = `<div class="error-state"><span>!</span><b>This review could not be completed.</b><p>${escapeHtml(error.message)}</p><button class="outline-button" id="retryButton">Try again</button></div>`;
    $("#retryButton").addEventListener("click", runReview);
    $("#caseRef").textContent = "REVIEW FAILED";
    $("#caseState").textContent = "Needs attention";
    $("#caseState").className = "case-state reject";
  } finally {
    button.disabled = false;
    button.classList.remove("running");
    button.querySelector("span:nth-child(2)").textContent = label;
    if (previousPdfUrl?.startsWith("blob:")) setTimeout(() => URL.revokeObjectURL(previousPdfUrl), 1200);
    refreshRunButton();
  }
}
function downloadJson(value, filename) {
  downloadBlob(new Blob([JSON.stringify(value, null, 2)], {type:"application/json"}), filename);
}
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function loadRuns() {
  const requestId = ++state.historyRequest;
  const params = new URLSearchParams({limit:"1000"});
  if (state.filter) params.set("status", state.filter);
  if (state.search) params.set("q", state.search);
  const runs = await getJson(`/api/runs?${params}`);
  if (requestId !== state.historyRequest) return;
  state.runs = runs;
  const body = $("#archiveRows");
  if (!runs.length) {
    body.innerHTML = "<tr><td colspan='7' class='empty-table'>No cases match this view yet.</td></tr>";
    $("#archiveDetail").innerHTML = "<div class='detail-empty'><span>↗</span><b>Choose a case to see the details.</b><small>The checks and source text are kept with the review.</small></div>";
    return;
  }
  body.innerHTML = runs.map(run => {
    const decision = run.result.decision;
    return `<tr data-id="${run.id}"><td>#${run.id}</td><td>${escapeHtml(run.invoice.vendor || "Supplier unknown")}</td><td>${escapeHtml(run.invoice.invoice_number || "—")}</td><td>${escapeHtml(money(run.invoice.total, run.invoice.currency))}</td><td><span class="outcome-tag ${outcomeClass(decision)}">${outcome(decision)[0]}</span></td><td>${escapeHtml(formatDate(run.created_at))}</td><td>↗</td></tr>`;
  }).join("");
  $$("#archiveRows tr[data-id]").forEach(row => row.addEventListener("click", () => openArchiveCase(Number(row.dataset.id))));
  openArchiveCase(runs[0].id);
}
function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}).format(date);
}
function openArchiveCase(id) {
  const run = state.runs.find(item => item.id === id);
  if (!run) return;
  $$("#archiveRows tr").forEach(row => row.classList.toggle("selected", Number(row.dataset.id) === id));
  const invoice = run.invoice, result = run.result, decision = outcome(result.decision);
  $("#archiveDetail").innerHTML = `<div class="detail-grid"><div class="detail-cell"><small>SUPPLIER</small><b>${escapeHtml(invoice.vendor || "Unknown")}</b></div><div class="detail-cell"><small>INVOICE REFERENCE</small><b>${escapeHtml(invoice.invoice_number || "Missing")}</b></div><div class="detail-cell"><small>OUTCOME · ${escapeHtml(decision[0].toUpperCase())}</small><b>${escapeHtml(money(invoice.total, invoice.currency))}</b></div></div><div class="detail-reason"><b>Why:</b> ${escapeHtml(result.reason)}<br><b>Next:</b> ${escapeHtml(result.next_step || "Use your usual AP review step.")}</div><button class="packet-button" id="archiveDownload">↓ Download this case packet</button>`;
  $("#archiveDownload").addEventListener("click", () => downloadJson(run, `mosaic-case-${run.id}.json`));
}
function renderPolicyCases() {
  $("#policyCases").innerHTML = state.samples.map(sample => `<article class="demo-case"><b>${escapeHtml(sample.title)}</b><small>${escapeHtml(sample.note)}</small><em>${sample.kind === "approve" ? "READY FOR HAND-OFF" : sample.kind === "stop" ? "STOPPED" : "IN REVIEW"}</em></article>`).join("");
}
const workStatuses = {NEW:"New", IN_REVIEW:"In review", WAITING:"Waiting", RESOLVED:"Resolved"};
function caseCode(id) { return `AP-${String(id).padStart(6,"0")}`; }
function renderQueue() {
  const status = $("#queueStatus").value, decision = $("#queueDecision").value;
  const query = $("#queueSearch").value.trim().toLowerCase();
  const openCount = state.queue.filter(item => item.status !== "RESOLVED").length;
  $("#queueCount").textContent = openCount;
  $("#navQueue").textContent = openCount;
  $("#navQueue").hidden = !openCount;
  const visible = state.queue.filter(item => (status === "OPEN" ? item.status !== "RESOLVED" : !status || item.status === status)
    && (!decision || item.result.decision === decision)
    && (!query || `${caseCode(item.id)} ${item.filename} ${item.invoice.vendor || ""} ${item.invoice.invoice_number || ""} ${item.assigned_to || ""}`.toLowerCase().includes(query)));
  if (!visible.length) {
    $("#queueRows").innerHTML = `<div class="queue-empty"><span>✳</span><b>Nothing in this slice</b><small>Change the filters or review a new invoice.</small></div>`;
    return;
  }
  $("#queueRows").innerHTML = visible.map(item => `<button class="queue-row ${state.currentQueueCase?.id === item.id ? "selected" : ""}" data-case-id="${item.id}">
    <span class="queue-case"><b>${caseCode(item.id)}</b><small>${escapeHtml(item.invoice.vendor || "Supplier not identified")} · ${escapeHtml(item.invoice.invoice_number || "Reference missing")}</small></span>
    <span class="queue-recommendation"><span class="outcome-tag ${outcomeClass(item.result.decision)}">${outcome(item.result.decision)[0]}</span>${item.decision_override ? `<small>Reviewer: ${escapeHtml(outcome(item.decision_override)[0])}</small>` : ""}</span>
    <span class="workflow-chip workflow-${item.status.toLowerCase()}">${escapeHtml(workStatuses[item.status] || item.status)}</span>
    <span class="queue-owner">${escapeHtml(item.assigned_to || "Unassigned")}</span>
    <b class="queue-amount">${escapeHtml(money(item.invoice.total,item.invoice.currency))}</b>
  </button>`).join("");
  $$(".queue-row").forEach(button => button.addEventListener("click", () => openWorkbench(Number(button.dataset.caseId))));
}
async function loadQueue() {
  state.queue = await getJson("/api/cases");
  renderQueue();
  if (state.currentQueueCase && state.queue.some(item => item.id === state.currentQueueCase.id)) {
    await openWorkbench(state.currentQueueCase.id, false);
  }
}
async function patchCase(id, changes) {
  const response = await fetch(`/api/cases/${id}`, {method:"PATCH",headers:{"Content-Type":"application/json",Accept:"application/json"},body:JSON.stringify(changes)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The case update could not be saved.");
  return data;
}
async function openWorkbench(id, refreshList = true) {
  state.currentQueueCase = await getJson(`/api/cases/${id}`);
  renderWorkbench(state.currentQueueCase);
  if (refreshList) renderQueue();
}
function renderWorkbench(item) {
  const decision = item.result.decision, balance = item.result.po_balance;
  const events = item.events || [];
  const fields = ["invoice_number","invoice_date","vendor","po_number","total","currency","subtotal","tax"];
  const displayValue = (key, value) => key === "total" || key === "subtotal" || key === "tax"
    ? (value == null ? "Not found" : money(value,item.invoice.currency)) : String(value ?? "Not found");
  const corrections = Object.entries(item.corrections || {});
  const evidenceRows = (item.result.checks || []).map(check => `<div class="source-check"><div><b>${escapeHtml(check.name)}</b><small>${escapeHtml(check.detail)}</small></div>${evidenceForCheck(check,item.invoice,item.result.matched_po)}</div>`).join("");
  const comparison = item.comparison ? `<section class="workbench-section version-card"><div class="wb-section-head"><span>01</span><div><b>Version comparison</b><small>Compared with case ${caseCode(item.comparison.case_id)}</small></div></div>${item.comparison.changes.length ? item.comparison.changes.map(change => `<div class="version-diff"><b>${escapeHtml(change.field.replaceAll("_"," "))}</b><span>${escapeHtml(String(change.before ?? "—"))}<i>→</i>${escapeHtml(String(change.after ?? "—"))}</span></div>`).join("") : "<p class='quiet-note'>The key invoice fields match the earlier submission.</p>"}</section>` : `<section class="workbench-section version-card"><div class="wb-section-head"><span>01</span><div><b>Version comparison</b><small>First submission for this reference</small></div></div><p class="quiet-note">A later submission with the same supplier and invoice number will appear here with field-level changes.</p></section>`;
  const timeline = balance ? `<section class="workbench-section balance-card"><div class="wb-section-head"><span>03</span><div><b>PO commitment timeline</b><small>${escapeHtml(balance.currency)} ${escapeHtml(balance.po_number || item.result.matched_po?.po_number || "")}</small></div></div><div class="balance-figure"><div class="balance-track"><i style="width:${Math.min(100,Math.max(0,balance.previously_approved/balance.commitment*100))}%"></i><i style="width:${Math.min(100,Math.max(0,balance.this_invoice/balance.commitment*100))}%"></i></div><div class="balance-legend"><span><i class="prior-dot"></i>Previously approved <b>${escapeHtml(money(balance.previously_approved,balance.currency))}</b></span><span><i class="current-dot"></i>This invoice <b>${escapeHtml(money(balance.this_invoice,balance.currency))}</b></span></div><div class="balance-summary"><span>Committed <b>${escapeHtml(money(balance.commitment,balance.currency))}</b></span><span>Remaining after review <b>${escapeHtml(money(balance.remaining_after,balance.currency))}</b></span></div></div></section>` : "";
  const correctionList = corrections.length ? corrections.map(([key,value]) => `<div class="correction-record"><b>${escapeHtml(key.replaceAll("_"," "))}</b><span>${escapeHtml(displayValue(key,value.original))} <i>→</i> ${escapeHtml(displayValue(key,value.corrected))}</span><small>${escapeHtml(value.rationale)}</small></div>`).join("") : "<p class='quiet-note'>Reviewer corrections become evaluation examples; the original extracted values stay in the audit trail.</p>";
  const eventList = events.slice().reverse().map(event => `<div class="audit-event"><i class="event-dot event-${escapeHtml(event.kind)}"></i><div><b>${escapeHtml(event.message)}</b><small>${escapeHtml(formatDate(event.created_at))}</small></div></div>`).join("");
  $("#caseWorkbench").innerHTML = `<div class="workbench-case-head"><div><span class="overline">${caseCode(item.id)} · REVIEW WORKBENCH</span><h2>${escapeHtml(item.invoice.vendor || "Supplier not identified")}</h2><p>${escapeHtml(item.invoice.invoice_number || "Invoice reference missing")} · ${escapeHtml(money(item.invoice.total,item.invoice.currency))}</p></div><span class="outcome-tag ${outcomeClass(decision)}">Model: ${outcome(decision)[0]}</span></div>
    <div class="work-state-form"><label>Work state<select id="wbStatus">${Object.entries(workStatuses).map(([key,label]) => `<option value="${key}" ${item.status===key?"selected":""}>${label}</option>`).join("")}</select></label><label>Assigned reviewer<input id="wbAssignee" maxlength="80" value="${escapeHtml(item.assigned_to)}" placeholder="Assign an owner"></label><button class="primary-small" id="saveWorkState">Save workflow</button></div>
    ${comparison}<section class="workbench-section source-card"><div class="wb-section-head"><span>02</span><div><b>Evidence behind the checks</b><small>Open a control to see its extracted source line or register value</small></div></div><div class="source-check-list">${evidenceRows || "<p class='quiet-note'>No source evidence was extracted for this case.</p>"}</div></section>${timeline}
    <section class="workbench-section disposition-card"><div class="wb-section-head"><span>04</span><div><b>Reviewer disposition</b><small>Override is separate from the model recommendation</small></div></div><div class="disposition-fields"><label>Final disposition<select id="wbOverride"><option value="">Keep model recommendation</option><option value="APPROVE" ${item.decision_override==="APPROVE"?"selected":""}>Ready for hand-off</option><option value="REVIEW" ${item.decision_override==="REVIEW"?"selected":""}>Needs a second look</option><option value="REJECT" ${item.decision_override==="REJECT"?"selected":""}>Stop safely</option></select></label><label>Reason for override<input id="wbOverrideReason" maxlength="500" value="${escapeHtml(item.override_rationale || "")}" placeholder="Required when changing the model recommendation"></label><button class="outline-button" id="saveOverride">Record disposition</button></div></section>
    <section class="workbench-section correction-card"><div class="wb-section-head"><span>05</span><div><b>Extraction feedback</b><small>Correct a field and explain the source</small></div></div><div class="correction-fields"><label>Field<select id="correctionField">${fields.map(key=>`<option value="${key}">${key.replaceAll("_"," ")}</option>`).join("")}</select></label><label>Correct value<input id="correctionValue" placeholder="Verified value"></label><label>Why is it different?<input id="correctionReason" maxlength="500" placeholder="e.g. OCR included a nearby PO number"></label><button class="outline-button" id="saveCorrection">Save correction</button></div><div class="correction-list">${correctionList}</div></section>
    <section class="workbench-section notes-card"><div class="wb-section-head"><span>06</span><div><b>Reviewer notes</b><small>Visible in the case packet and audit trail</small></div></div><textarea id="caseNote" maxlength="2000" placeholder="Add context, a request to procurement, or the next follow-up…"></textarea><button class="primary-small" id="saveNote">Add note</button></section>
    <section class="workbench-section audit-card"><div class="wb-section-head"><span>07</span><div><b>Activity trail</b><small>Who changed what and when</small></div><button class="link-button" id="downloadAudit">Download audit JSON ↓</button></div><div class="audit-timeline">${eventList || "<p class='quiet-note'>No activity recorded.</p>"}</div></section>`;
  $("#saveWorkState").addEventListener("click", async () => {
    try { state.currentQueueCase = await patchCase(item.id,{status:$("#wbStatus").value,assigned_to:$("#wbAssignee").value}); renderWorkbench(state.currentQueueCase); await loadQueue(); toast("Workflow saved to the audit trail."); }
    catch(error) { toast(error.message); }
  });
  $("#saveOverride").addEventListener("click", async () => {
    try { state.currentQueueCase = await patchCase(item.id,{decision_override:$("#wbOverride").value,override_rationale:$("#wbOverrideReason").value}); renderWorkbench(state.currentQueueCase); await loadQueue(); toast("Reviewer disposition recorded."); }
    catch(error) { toast(error.message); }
  });
  $("#saveCorrection").addEventListener("click", async () => {
    const field = $("#correctionField").value, input = $("#correctionValue");
    if (!input.value.trim()) { toast("Enter the corrected value first."); input.focus(); return; }
    try { state.currentQueueCase = await patchCase(item.id,{correction:{field,value:field==="total"||field==="subtotal"||field==="tax"?Number(input.value):input.value,rationale:$("#correctionReason").value}}); renderWorkbench(state.currentQueueCase); toast("Correction saved as evaluation feedback."); }
    catch(error) { toast(error.message); }
  });
  const syncCorrectionInput = () => {
    const key = $("#correctionField").value, input = $("#correctionValue"), numeric = ["total","subtotal","tax"].includes(key);
    input.type = numeric ? "number" : "text";
    input.step = numeric ? "0.01" : "any";
    input.value = item.corrections?.[key]?.corrected ?? item.invoice[key] ?? "";
  };
  $("#correctionField").addEventListener("change",syncCorrectionInput);
  syncCorrectionInput();
  $("#saveNote").addEventListener("click", async () => {
    try { state.currentQueueCase = await patchCase(item.id,{note:$("#caseNote").value}); renderWorkbench(state.currentQueueCase); await loadQueue(); toast("Note added to the case history."); }
    catch(error) { toast(error.message); }
  });
  $("#downloadAudit").addEventListener("click", () => downloadJson(item,`mosaic-audit-${item.id}.json`));
}
function renderPos() {
  $("#poCount").textContent = state.pos.length;
  $("#poModalTable").innerHTML = state.pos.map(po => `<div class="po-row"><span>${escapeHtml(po.po_number)}</span><b>${escapeHtml(po.vendor)}</b><small>${escapeHtml(money(po.approved_amount, po.currency))}</small><em>${escapeHtml(po.status)}</em></div>`).join("");
}
function showCommandMenu() {
  $("#commandBackdrop").hidden = false;
  $("#commandSearch").value = "";
  state.commandIndex = 0;
  renderCommandResults();
  $("#commandSearch").focus();
}
function hideCommandMenu() { $("#commandBackdrop").hidden = true; }
function renderCommandResults() {
  const query = $("#commandSearch").value.trim().toLowerCase();
  const filtered = commands.filter(command => `${command.title} ${command.detail} ${command.keywords}`.toLowerCase().includes(query));
  state.visibleCommands = filtered;
  state.commandIndex = Math.min(state.commandIndex, Math.max(0, filtered.length - 1));
  $("#commandResults").innerHTML = filtered.length ? filtered.map((command, index) => `
    <button class="command-option ${index === state.commandIndex ? "active" : ""}" data-command-index="${index}">
      <span>${command.icon}</span><span><b>${escapeHtml(command.title)}</b><small>${escapeHtml(command.detail)}</small></span>${index === state.commandIndex ? "<kbd>ENTER</kbd>" : ""}
    </button>`).join("") : "<div class='command-empty'>No action matches that phrase.</div>";
  $$(".command-option").forEach(button => button.addEventListener("click", () => runCommand(Number(button.dataset.commandIndex))));
}
function runCommand(index) {
  const command = state.visibleCommands?.[index];
  if (!command) return;
  hideCommandMenu();
  command.run();
}
function setTolerance(value) {
  state.tolerance = Math.max(0, Math.min(10, Number(value) || 0));
  $("#tolerance").value = state.tolerance;
  $("#toleranceValue").textContent = `${state.tolerance.toFixed(1)}%`;
  try { localStorage.setItem("mosaic.tolerance", String(state.tolerance)); } catch { /* Storage is optional in private browsing. */ }
}
async function init() {
  $("#today").textContent = new Intl.DateTimeFormat(undefined, {weekday:"short", month:"short", day:"numeric"}).format(new Date());
  try { setTolerance(localStorage.getItem("mosaic.tolerance") ?? 2); } catch { setTolerance(2); }
  $("#runButton").addEventListener("click", runReview);
  $("#tolerance").addEventListener("input", event => setTolerance(event.target.value));
  $$(".nav-item").forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
  $$('[data-goto]').forEach(button => button.addEventListener("click", () => setView(button.dataset.goto)));
  $("#viewPO").addEventListener("click", () => { $("#modalBackdrop").hidden = false; });
  $("#modalClose").addEventListener("click", () => { $("#modalBackdrop").hidden = true; });
  $("#modalBackdrop").addEventListener("click", event => { if (event.target.id === "modalBackdrop") event.currentTarget.hidden = true; });
  $("#helpButton").addEventListener("click", showCommandMenu);
  $("#commandSearch").addEventListener("input", () => { state.commandIndex = 0; renderCommandResults(); });
  $("#commandBackdrop").addEventListener("click", event => { if (event.target.id === "commandBackdrop") hideCommandMenu(); });
  $("#commandBackdrop").addEventListener("keydown", event => {
    const count = state.visibleCommands?.length || 0;
    if (event.key === "ArrowDown" && count) { event.preventDefault(); state.commandIndex = (state.commandIndex + 1) % count; renderCommandResults(); }
    if (event.key === "ArrowUp" && count) { event.preventDefault(); state.commandIndex = (state.commandIndex - 1 + count) % count; renderCommandResults(); }
    if (event.key === "Enter") { event.preventDefault(); runCommand(state.commandIndex); }
  });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); showCommandMenu(); }
    if (event.key === "Escape") { hideCommandMenu(); $("#modalBackdrop").hidden = true; }
    if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      event.preventDefault(); setView("history"); setTimeout(() => $("#searchRuns").focus(), 0);
    }
    if (!["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName) && $("#view-queue").classList.contains("active")) {
      const rows = $$(".queue-row");
      const current = rows.findIndex(row=>Number(row.dataset.caseId)===state.currentQueueCase?.id);
      if (["j","k"].includes(event.key.toLowerCase()) && rows.length) {
        event.preventDefault(); rows[(current + (event.key.toLowerCase()==="j"?1:-1) + rows.length)%rows.length].click();
      } else if (event.key.toLowerCase()==="n") $("#caseNote")?.focus();
      else if (event.key.toLowerCase()==="e") $("#wbStatus")?.focus();
    }
  });
  $("#invoiceFile").addEventListener("change", event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) { toast("Please choose a PDF invoice."); event.target.value = ""; return; }
    if (file.size > 15 * 1024 * 1024) { toast("This demo accepts PDFs up to 15 MB."); event.target.value = ""; return; }
    state.file = file; state.selected = null; renderScenarios();
    $("#filePill").hidden = false; $("#filePill").textContent = file.name;
    $("#uploadTitle").textContent = "PDF ready to review";
    $("#uploadHelp").textContent = "Ready to review";
    refreshRunButton();
    toast("PDF ready. Review invoice is now available.");
    event.target.value = "";
  });
  const dropzone = $("#dropzone");
  dropzone.addEventListener("click", () => $("#invoiceFile").click());
  ["dragenter", "dragover"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove("dragover"); }));
  dropzone.addEventListener("drop", event => {
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    const transfer = new DataTransfer(); transfer.items.add(file);
    const input = $("#invoiceFile"); input.files = transfer.files; input.dispatchEvent(new Event("change", {bubbles:true}));
  });
  $("#searchRuns").addEventListener("input", event => {
    state.search = event.target.value;
    clearTimeout(init.searchTimer);
    init.searchTimer = setTimeout(() => loadRuns().catch(error => toast(error.message)), 220);
  });
  $("#filterRuns").addEventListener("change", event => { state.filter = event.target.value; loadRuns().catch(error => toast(error.message)); });
  $("#queueStatus").addEventListener("change", renderQueue);
  $("#queueDecision").addEventListener("change", renderQueue);
  $("#queueSearch").addEventListener("input", renderQueue);
  $("#exportRuns").addEventListener("click", async () => {
    try {
      const runs = await getJson("/api/runs?limit=1000");
      const rows = [["Case", "Supplier", "Invoice", "Amount", "Currency", "Model recommendation", "Reviewer disposition", "Work state", "Assigned to", "Override rationale", "Reason", "Reviewed"],
        ...runs.map(run => [run.id, run.invoice.vendor || "", run.invoice.invoice_number || "", run.invoice.total ?? "", run.invoice.currency || "", run.result.decision, run.decision_override || run.result.decision, run.status, run.assigned_to, run.override_rationale, run.result.reason, run.created_at])];
      const csv = rows.map(row => row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n");
      downloadBlob(new Blob([csv], {type:"text/csv"}), "mosaic-case-archive.csv");
    } catch (error) { toast(error.message); }
  });
  loadWorkspace();
}

async function loadWorkspace() {
  try {
    const [samples, pos, summary] = await Promise.all([getJson("/api/samples"), getJson("/api/pos"), getJson("/api/summary")]);
    state.samples = samples; state.pos = pos;
    renderScenarios(); renderPos(); renderPolicyCases(); renderSummary(summary);
    loadQueue().catch(error => toast(error.message));
  } catch (error) {
    toast(error.message || "Mosaic could not be reached.");
    $("#scenarioList").innerHTML = `<div class="workspace-retry"><span class="recent-empty">Prepared invoices are unavailable right now.</span><button class="outline-button" id="retryWorkspace">Retry connection</button></div>`;
    $("#retryWorkspace").addEventListener("click", event => {
      event.currentTarget.disabled = true;
      event.currentTarget.textContent = "Checking…";
      loadWorkspace();
    });
  }
}
window.addEventListener("beforeunload", () => {
  if (state.currentPdfUrl?.startsWith("blob:")) URL.revokeObjectURL(state.currentPdfUrl);
});
init();
