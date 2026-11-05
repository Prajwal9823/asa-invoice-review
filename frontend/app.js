// Mosaic AP Enterprise · Intelligent Accounts Payable Frontend Engine
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  samples: [],
  pos: [],
  grns: [],
  vendors: [],
  runs: [],
  queue: [],
  currentQueueCase: null,
  currentWorkbenchCase: null,
  selected: null,
  file: null,
  latest: null,
  filter: "",
  search: "",
  tolerance: 2.0,
  historyRequest: 0,
  commandIndex: 0,
  currentPdfUrl: null,
  aiMessages: [],
  notifications: { unread_count: 0, critical_cases: [], unassigned_cases: [] }
};

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

const money = (amount, currency = "USD") => {
  if (amount == null) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 2
    }).format(amount);
  } catch {
    return `${currency} ${Number(amount).toFixed(2)}`;
  }
};

const outcomeInfo = decision => {
  switch (decision) {
    case "APPROVE":
      return { label: "Ready for Hand-Off", class: "badge-approve", tagClass: "tag-approve", icon: "✓" };
    case "REJECT":
      return { label: "Stopped Safely", class: "badge-reject", tagClass: "tag-reject", icon: "✕" };
    default:
      return { label: "Needs Review", class: "badge-review", tagClass: "tag-review", icon: "◷" };
  }
};

const riskBadgeClass = level => {
  switch (String(level).toUpperCase()) {
    case "CRITICAL": return "risk-critical";
    case "HIGH": return "risk-high";
    case "MODERATE": return "risk-moderate";
    default: return "risk-low";
  }
};

const priorityBadgeClass = priority => {
  switch (String(priority).toUpperCase()) {
    case "CRITICAL": return "priority-critical";
    case "HIGH": return "priority-high";
    case "LOW": return "priority-low";
    default: return "priority-medium";
  }
};

const caseCode = id => `AP-${String(id).padStart(6, "0")}`;

const formatDate = value => {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit"
  }).format(d);
};

// Session & API Helpers
function getSessionId() {
  let sid = localStorage.getItem("mosaic.session_id");
  if (!sid || !/^[a-zA-Z0-9_-]{8,64}$/.test(sid)) {
    sid = "sess_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    localStorage.setItem("mosaic.session_id", sid);
  }
  return sid;
}

async function getJson(url) {
  let response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: "application/json",
        "X-Session-ID": getSessionId()
      }
    });
  } catch {
    throw new Error(`Cannot reach ${url}. Check that Mosaic AP server is running.`);
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Mosaic AP server returned an invalid response for ${url}.`);
  }
  if (!response.ok) throw new Error(data.error || "Request failed.");
  return data;
}

async function resetWorkspaceSession() {
  if (!confirm("Clear workspace to a completely clean slate (0 cases)? This clears the exception queue and history so you can review invoices from scratch.")) return;
  try {
    toast("Clearing workspace...");
    const res = await fetch("/api/session/reset", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-Session-ID": getSessionId()
      }
    });
    if (!res.ok) throw new Error("Server failed to reset session");
    toast("Workspace cleared to 0 cases. Ready for clean intake.");
    state.currentCase = null;
    state.currentQueueCase = null;
    state.currentWorkbenchCase = null;
    state.latest = null;
    state.file = null;
    $("#deskResult").innerHTML = `<div class="recent-empty">Select a scenario or upload a PDF to begin review.</div>`;
    $("#caseTopline").hidden = true;
    await loadWorkspace();
    renderQueue();
    setView("desk");
  } catch (err) {
    toast(`Failed to reset: ${err.message}`);
  }
}

async function loadDemoDataset() {
  try {
    toast("Loading pre-populated demo cases...");
    const res = await fetch("/api/session/seed", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-Session-ID": getSessionId()
      }
    });
    if (!res.ok) throw new Error("Failed to load demo data");
    toast("Demo dataset loaded with 3 active exceptions & 3 resolved cases.");
    await loadWorkspace();
    renderQueue();
  } catch (err) {
    toast(`Failed to load demo: ${err.message}`);
  }
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 3200);
}

function downloadJson(value, filename) {
  downloadBlob(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }), filename);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Navigation & View Routing
function setView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-item").forEach(button => {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });

  const labels = {
    desk: "Review Desk",
    queue: "Exception Queue",
    workbench: "Review Workbench",
    vendors: "Vendor Intelligence",
    history: "Case History",
    analytics: "Analytics Dashboard",
    policy: "How it Works"
  };
  $("#crumbTitle").textContent = labels[name] || "Review Desk";

  if (name === "history") loadRuns().catch(err => toast(err.message));
  if (name === "queue") loadQueue().catch(err => toast(err.message));
  if (name === "analytics") getJson("/api/summary").then(renderAnalytics).catch(err => toast(err.message));
  if (name === "vendors") renderVendors();
  if (name === "policy") renderPolicyCases();

  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Review Desk & Intake Handling
function setSelected(file) {
  state.selected = file;
  state.file = null;
  $("#invoiceFile").value = "";
  $("#filePill").hidden = true;
  $("#uploadTitle").textContent = "Drag & Drop Invoice PDF Here";
  $("#uploadHelp").textContent = "Supports text-readable digital PDFs up to 15 MB";

  renderScenarios();
  refreshRunButton();

  // Highlight quick glance if scenario found
  const sample = state.samples.find(s => s.file === file);
  if (sample) {
    $("#quickInvoice").textContent = sample.title;
    $("#quickAmount").textContent = "Ready to evaluate";
    $("#quickDate").textContent = "—";
  }
}

function renderScenarios() {
  const list = $("#scenarioList");
  if (!state.samples.length) {
    list.innerHTML = "<div class='recent-empty'>No sample invoices found in data/invoices.</div>";
    return;
  }
  const activeSample = state.samples.find(s => s.file === state.selected);
  $("#sampleCount").textContent = activeSample ? activeSample.title : `${state.samples.length} enterprise scenarios available`;

  list.innerHTML = state.samples.map(sample => `
    <div class="scenario-card ${state.selected === sample.file ? "selected" : ""}"
         data-file="${escapeHtml(sample.file)}" role="option" aria-selected="${state.selected === sample.file}">
      <span class="scenario-icon">PDF</span>
      <div class="scenario-info">
        <b>${escapeHtml(sample.title)}</b>
        <small>${escapeHtml(sample.note)}</small>
      </div>
      <span class="scenario-status-pill status-${escapeHtml(sample.kind)}"></span>
    </div>
  `).join("");

  $$(".scenario-card", list).forEach(card => {
    card.addEventListener("click", () => {
      setSelected(card.dataset.file);
      toast(`Selected: ${card.querySelector("b").textContent}`);
    });
  });
}

function refreshRunButton() {
  const button = $("#runButton");
  button.disabled = !(state.selected || state.file) || button.classList.contains("running");
  const label = state.file
    ? `Review “${state.file.name}”`
    : state.selected
    ? `Review ${state.samples.find(s => s.file === state.selected)?.title || "Invoice"}`
    : "Review Invoice";
  button.querySelector("span:nth-child(2)").textContent = label;
}

function renderLoading() {
  $("#caseTopline").hidden = false;
  $("#caseRef").textContent = "REVIEW IN PROGRESS";
  $("#caseState").textContent = "Evaluating 3-Way Match & Controls";
  $("#caseState").className = "badge badge-review";
  $("#caseTier").textContent = "Calculating Tier…";

  $("#evidenceCanvas").innerHTML = `
    <div class="processing">
      <div class="processing-mark"></div>
      <b>Processing Invoice Documents</b>
      <small style="color: var(--text-dim); margin-top: 4px;">Running deterministic controls, 3-way matching, and risk analysis</small>
      <div class="processing-steps">
        <div class="processing-step done"><span class="process-indicator">✓</span>Cryptographic SHA-256 fingerprinting</div>
        <div class="processing-step done"><span class="process-indicator">✓</span>Extracting line items, tax, and remit details</div>
        <div class="processing-step current"><span class="process-indicator">●</span>Three-way reconciliation against PO & Goods Receipt (GRN)</div>
        <div class="processing-step"><span class="process-indicator">○</span>Explainable risk scoring & audit dossier generation</div>
      </div>
    </div>
  `;
}

async function runReview() {
  const button = $("#runButton");
  button.disabled = true;
  button.classList.add("running");
  const originalLabel = button.querySelector("span:nth-child(2)").textContent;
  const previousPdfUrl = state.currentPdfUrl;

  state.currentPdfUrl = state.file
    ? URL.createObjectURL(state.file)
    : `/api/sample/${encodeURIComponent(state.selected || "")}?session=${encodeURIComponent(getSessionId())}`;

  renderLoading();

  try {
    await new Promise(r => setTimeout(r, 450)); // smooth step transition

    const tolerance = encodeURIComponent(state.tolerance);
    const response = state.file
      ? await (() => {
          const form = new FormData();
          form.append("invoice", state.file);
          return fetch(`/api/upload?tolerance=${tolerance}`, {
            method: "POST",
            headers: { "X-Session-ID": getSessionId() },
            body: form
          });
        })()
      : await fetch(`/api/review?sample=${encodeURIComponent(state.selected)}&tolerance=${tolerance}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Session-ID": getSessionId()
          },
          body: "{}"
        });

    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Review failed.");

    state.latest = payload;
    state.currentWorkbenchCase = payload.case || payload;

    renderDeskResult(payload);
    renderSummary(await getJson("/api/summary"));
    await loadRuns();
    await loadQueue().catch(() => {});
    await checkNotifications();

    toast(`Review complete for Case #${payload.id}. Controls verified.`);
  } catch (error) {
    $("#evidenceCanvas").innerHTML = `
      <div class="empty-case" style="border-color: var(--rose-border); background: var(--rose-bg);">
        <div style="color: var(--rose); font-size: 28px; font-weight: 800;">✕</div>
        <strong>Review Could Not Be Completed</strong>
        <span>${escapeHtml(error.message)}</span>
        <button class="btn btn-secondary btn-sm" id="retryButton" style="margin-top: 12px;">Try Again</button>
      </div>
    `;
    $("#retryButton")?.addEventListener("click", runReview);
    $("#caseRef").textContent = "REVIEW FAILED";
    $("#caseState").textContent = "Needs Attention";
    $("#caseState").className = "badge badge-reject";
  } finally {
    button.disabled = false;
    button.classList.remove("running");
    button.querySelector("span:nth-child(2)").textContent = originalLabel;
    if (previousPdfUrl?.startsWith("blob:")) setTimeout(() => URL.revokeObjectURL(previousPdfUrl), 1500);
    refreshRunButton();
  }
}

function renderDeskResult(data) {
  const invoice = data.invoice || {};
  const result = data.result || {};
  const po = result.matched_po;
  const tw = result.three_way_match || {};
  const risk = result.risk_engine || {};
  const checks = result.checks || [];
  const dec = outcomeInfo(result.decision);
  const code = caseCode(data.id);

  $("#caseTopline").hidden = false;
  $("#caseRef").textContent = code;
  $("#caseState").textContent = dec.label;
  $("#caseState").className = `badge ${dec.class}`;
  $("#caseTier").textContent = result.approval_tier || "Tier 1: Standard Review";

  $("#quickInvoice").textContent = invoice.invoice_number || "Reference Missing";
  $("#quickAmount").textContent = money(invoice.total, invoice.currency);
  $("#quickDate").textContent = invoice.invoice_date || "—";
  $("#quickPO").textContent = po ? po.po_number : (invoice.po_number || "None");

  const pdfUrl = state.currentPdfUrl;
  const conf = invoice.field_confidence || {};

  const checkRows = checks.map(c => `
    <div class="review-check ${c.status}">
      <span class="check-mark">${c.status === "pass" ? "✓" : c.status === "fail" ? "✕" : "·"}</span>
      <div class="check-copy">
        <b>${escapeHtml(c.name)}</b>
        <small>${escapeHtml(c.detail)}</small>
      </div>
      <span class="badge ${c.status === "pass" ? "badge-approve" : c.status === "fail" ? "badge-reject" : "badge-review"}">${c.status.toUpperCase()}</span>
    </div>
  `).join("");

  const poBalance = result.po_balance;
  const balanceHtml = poBalance ? `
    <div class="po-meter-wrap" style="margin-top: 10px;">
      <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim);">
        <span>Previously Approved: <b>${money(poBalance.previously_approved, poBalance.currency)}</b></span>
        <span>Remaining: <b>${money(poBalance.remaining_after, poBalance.currency)}</b></span>
      </div>
      <div class="po-meter" style="margin-top: 4px;">
        <div class="po-meter-bar" style="width: ${Math.min(100, Math.max(0, (poBalance.previously_approved + poBalance.this_invoice) / poBalance.commitment * 100))}%;"></div>
      </div>
    </div>
  ` : "";

  $("#evidenceCanvas").innerHTML = `
    <div class="evidence-layout">
      <!-- Col 1: Invoice Document & Extracted Fields -->
      <section class="review-column">
        <div class="review-column-head">
          <span class="column-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
          </span>
          <div>
            <b>Source Document & Extracted Fields</b>
            <small>Text extraction confidence evaluated</small>
          </div>
        </div>

        ${pdfUrl ? `
          <div class="invoice-preview">
            <iframe class="invoice-iframe" src="${escapeHtml(pdfUrl)}#toolbar=0&navpanes=0&view=FitH" title="Invoice Preview"></iframe>
          </div>
        ` : `
          <div class="invoice-preview" style="display:grid; place-items:center; color:var(--text-dim); font-size:12px;">
            Document preview not cached for this view.
          </div>
        `}

        <details class="extracted-details" open>
          <summary>Extracted Line & Metadata Fields</summary>
          <div class="invoice-fields-grid">
            <div class="field-cell"><small>Supplier (${Math.round((conf.vendor || 0.95)*100)}% conf)</small><b>${escapeHtml(invoice.vendor || "Not found")}</b></div>
            <div class="field-cell"><small>Invoice Ref (${Math.round((conf.invoice_number || 0.98)*100)}% conf)</small><b>${escapeHtml(invoice.invoice_number || "Not found")}</b></div>
            <div class="field-cell"><small>Date (${Math.round((conf.invoice_date || 0.9)*100)}% conf)</small><b>${escapeHtml(invoice.invoice_date || "Not found")}</b></div>
            <div class="field-cell"><small>PO Ref (${Math.round((conf.po_number || 0.9)*100)}% conf)</small><b>${escapeHtml(invoice.po_number || "Not found")}</b></div>
            <div class="field-cell"><small>Subtotal</small><b>${money(invoice.subtotal, invoice.currency)}</b></div>
            <div class="field-cell"><small>Tax</small><b>${money(invoice.tax, invoice.currency)}</b></div>
            <div class="field-cell" style="grid-column: 1/-1; background: var(--primary-light);"><small style="color:var(--primary-dark)">Total Payable (${Math.round((conf.total || 0.98)*100)}% conf)</small><b style="font-size:14px; color:var(--primary-dark)">${money(invoice.total, invoice.currency)}</b></div>
          </div>
        </details>
      </section>

      <!-- Col 2: Three-Way Match & PO Commitment -->
      <section class="review-column">
        <div class="review-column-head">
          <span class="column-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
          </span>
          <div>
            <b>Three-Way Reconciliation (PO / GRN)</b>
            <small>${tw.status_label || "Evaluated"}</small>
          </div>
        </div>

        ${po ? `
          <div class="po-sheet">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
              <span class="po-number-tag">${escapeHtml(po.po_number)}</span>
              <span class="badge ${po.status === 'approved' ? 'badge-approve' : 'badge-review'}">${po.status.toUpperCase()}</span>
            </div>
            <b style="font-size:14px; color:var(--text-main);">${escapeHtml(po.vendor)}</b>
            <div class="po-facts">
              <div><small>Currency</small><b>${escapeHtml(po.currency)}</b></div>
              <div><small>PO Commitment</small><b>${money(po.approved_amount, po.currency)}</b></div>
              <div><small>Invoiced Value</small><b>${money(invoice.total, invoice.currency)}</b></div>
            </div>
            ${balanceHtml}
          </div>

          <div style="margin-top: 14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-size:11px; font-weight:700; color:var(--text-dim); text-transform:uppercase;">Line Item 3-Way Match</span>
              <span class="badge ${tw.status === 'MATCHED' ? 'badge-approve' : 'badge-review'}">${tw.status_label || 'Reconciled'}</span>
            </div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">
              ${(tw.lines || []).length} line items reconciled against Purchase Order and Goods Receipt Notes (GRNs).
              ${tw.discrepancy_amount ? `<div style="color:var(--rose); font-weight:700; margin-top:4px;">Discrepancy: $${tw.discrepancy_amount.toFixed(2)}</div>` : ''}
            </div>
          </div>
        ` : `
          <div class="po-sheet" style="background:#fffafa; border-color:var(--rose-border);">
            <span class="po-number-tag" style="background:#fee2e2; color:#991b1b;">No Approved PO</span>
            <p style="font-size:12px; color:var(--text-dim); margin-top:8px;">No confirmed purchasing commitment is linked to this invoice.</p>
          </div>
        `}
      </section>

      <!-- Col 3: Controls & Explainable Risk Score -->
      <section class="review-column">
        <div class="review-column-head">
          <span class="column-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
          </span>
          <div>
            <b>Automated Controls & Risk Engine</b>
            <small>Explainable score & next steps</small>
          </div>
        </div>

        <!-- Risk Score Strip -->
        <div class="risk-meter-container" style="margin-bottom: 14px; padding: 12px;">
          <div class="risk-score-circle ${risk.level === 'CRITICAL' ? 'risk-circle-critical' : risk.level === 'HIGH' ? 'risk-circle-high' : risk.level === 'MODERATE' ? 'risk-circle-moderate' : 'risk-circle-low'}" style="width:54px; height:54px; font-size:16px;">
            ${risk.score ?? 0}
          </div>
          <div style="flex:1;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <b style="font-size:13px; color:var(--text-main);">Risk Assessment</b>
              <span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.level || 'LOW'} RISK</span>
            </div>
            <small style="display:block; font-size:11px; color:var(--text-dim); margin-top:2px;">${risk.explanation || 'Controls evaluated.'}</small>
          </div>
        </div>

        <div class="review-check-list">${checkRows}</div>

        <div class="decision-result ${dec.class.replace('badge-', '')}">
          <div class="decision-icon">${dec.icon}</div>
          <div class="decision-text">
            <b>${dec.label}</b>
            <p>${escapeHtml(result.reason || "Review controls.")}</p>
          </div>
        </div>

        <div style="display:flex; gap:8px; margin-top:auto;">
          <button class="btn btn-primary" id="openWorkbenchBtn" style="flex:1;">Open in Review Workbench ↗</button>
          <a class="btn btn-secondary" href="/api/report/${data.id}" target="_blank" rel="noreferrer" title="Download printable review dossier">Dossier ↓</a>
        </div>
      </section>
    </div>
  `;

  $("#jumpToWorkbench")?.addEventListener("click", () => openWorkbench(data.id));
  $("#openWorkbenchBtn")?.addEventListener("click", () => openWorkbench(data.id));
}

// Exception Queue
async function loadQueue() {
  state.queue = await getJson("/api/cases");
  renderQueue();
  if (state.currentQueueCase) {
    const fresh = state.queue.find(c => c.id === state.currentQueueCase.id);
    if (fresh) renderQuickTriage(fresh);
  }
}

function renderQueue() {
  const status = $("#queueStatus").value;
  const decision = $("#queueDecision").value;
  const priority = $("#queuePriority")?.value || "";
  const query = $("#queueSearch").value.trim().toLowerCase();

  const openCases = state.queue.filter(c => c.status !== "RESOLVED");
  const criticalCases = state.queue.filter(c => c.priority === "CRITICAL" || c.result?.risk_engine?.level === "CRITICAL");
  const totalValueAtRisk = openCases.reduce((sum, c) => sum + (c.invoice.total || 0), 0);

  $("#qStatOpen").textContent = openCases.length;
  $("#qStatCritical").textContent = criticalCases.length;
  $("#qStatValue").textContent = money(totalValueAtRisk, "USD");
  $("#navQueue").textContent = openCases.length;
  $("#navQueue").hidden = !openCases.length;

  const visible = state.queue.filter(item => {
    if (status === "OPEN" && item.status === "RESOLVED") return false;
    if (status && status !== "OPEN" && item.status !== status) return false;
    if (decision && item.result.decision !== decision) return false;
    if (priority && (item.priority || "MEDIUM") !== priority) return false;
    if (query) {
      const hay = `${caseCode(item.id)} ${item.filename} ${item.invoice.vendor || ""} ${item.invoice.invoice_number || ""} ${item.assigned_to || ""}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  const rowsNode = $("#queueRows");
  if (!visible.length) {
    if (!state.queue.length) {
      rowsNode.innerHTML = `
        <div class="empty-queue-box" style="text-align:center; padding:48px 20px; border:1px dashed var(--border-light); border-radius:var(--radius-lg); margin-top:12px; background:var(--bg-card);">
          <div style="font-size:32px; margin-bottom:8px;">✓</div>
          <b style="font-size:15px; color:var(--text-main); display:block; margin-bottom:6px;">All Clear · No Open Exceptions</b>
          <p style="font-size:12.5px; color:var(--text-dim); max-width:440px; margin:0 auto 16px;">
            All invoices have cleared controls, or no pending exceptions are currently waiting in the queue.
          </p>
          <div style="display:inline-flex; gap:10px;">
            <button class="btn btn-primary btn-sm" id="btnGoDesk">Go to Review Desk</button>
            <button class="btn btn-secondary btn-sm" id="btnQuickSeed">Load Sample Dataset</button>
          </div>
        </div>
      `;
      $("#btnGoDesk")?.addEventListener("click", () => setView("desk"));
      $("#btnQuickSeed")?.addEventListener("click", loadDemoDataset);
      $("#quickTriagePanel").innerHTML = `<div class="workbench-empty"><b>No open exception selected.</b><p style="font-size:12px; color:var(--text-dim); margin-top:4px;">Process an invoice on the Review Desk or load sample data.</p></div>`;
    } else {
      rowsNode.innerHTML = `<div class="recent-empty">No exception cases match the selected filter criteria.</div>`;
      $("#quickTriagePanel").innerHTML = `<div class="workbench-empty"><b>No matching case selected.</b></div>`;
    }
    return;
  }

  rowsNode.innerHTML = visible.map(item => {
    const dec = outcomeInfo(item.result.decision);
    const risk = item.result.risk_engine || { score: 0, level: "LOW" };
    const prio = item.priority || "MEDIUM";
    const isSelected = state.currentQueueCase?.id === item.id;

    return `
      <button class="queue-row ${isSelected ? "selected" : ""}" data-case-id="${item.id}">
        <div class="queue-case-info">
          <b>${caseCode(item.id)}</b>
          <small>${escapeHtml(item.invoice.vendor || "Supplier not identified")}</small>
        </div>
        <div><span class="priority-chip ${priorityBadgeClass(prio)}">${prio}</span></div>
        <div><span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.score}/100</span></div>
        <div><span class="badge ${dec.class}">${dec.label}</span></div>
        <div><span class="workflow-chip workflow-${(item.status || "NEW").toLowerCase()}">${(item.status || "NEW").replace('_', ' ')}</span></div>
        <div style="font-size:12px; color:var(--text-muted);">${escapeHtml(item.assigned_to || "Unassigned")}</div>
        <b style="font-family:var(--font-mono); font-size:12.5px;">${money(item.invoice.total, item.invoice.currency)}</b>
      </button>
    `;
  }).join("");

  $$(".queue-row", rowsNode).forEach(row => {
    row.addEventListener("click", () => {
      const id = Number(row.dataset.caseId);
      const item = state.queue.find(c => c.id === id);
      if (item) {
        state.currentQueueCase = item;
        $$(".queue-row", rowsNode).forEach(r => r.classList.toggle("selected", Number(r.dataset.caseId) === id));
        renderQuickTriage(item);
      }
    });
  });

  // Default select first item
  if (!state.currentQueueCase || !visible.some(c => c.id === state.currentQueueCase.id)) {
    state.currentQueueCase = visible[0];
  }
  if (state.currentQueueCase) {
    $$(".queue-row", rowsNode).forEach(r => r.classList.toggle("selected", Number(r.dataset.caseId) === state.currentQueueCase.id));
    renderQuickTriage(state.currentQueueCase);
  }
}

function renderQuickTriage(item) {
  const panel = $("#quickTriagePanel");
  const invoice = item.invoice;
  const result = item.result;
  const risk = result.risk_engine || {};
  const tw = result.three_way_match || {};
  const code = caseCode(item.id);

  panel.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; border-bottom:1px solid var(--border-light); padding-bottom:10px;">
      <div>
        <div class="overline">${code} · TRIAGE</div>
        <h3 style="font-size:16px; font-weight:700; color:var(--text-main); margin:2px 0;">${escapeHtml(invoice.vendor || "Supplier not identified")}</h3>
        <span style="font-size:12px; color:var(--text-dim);">${escapeHtml(invoice.invoice_number || "No Ref")} · ${money(invoice.total, invoice.currency)}</span>
      </div>
      <span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.score ?? 0}/100</span>
    </div>

    <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:16px;">
      <div style="background:var(--bg-surface); padding:8px 10px; border-radius:var(--radius-sm); font-size:12px;">
        <span style="color:var(--text-dim); display:block; font-size:10px; font-weight:700;">PRIMARY CAUSE:</span>
        <b style="color:var(--text-main);">${escapeHtml(result.reason || "Review required.")}</b>
      </div>
      <div style="background:var(--bg-surface); padding:8px 10px; border-radius:var(--radius-sm); font-size:12px;">
        <span style="color:var(--text-dim); display:block; font-size:10px; font-weight:700;">RECOMMENDED ACTION:</span>
        <span style="color:var(--text-muted);">${escapeHtml(result.next_step || "Check supplier record.")}</span>
      </div>
      ${tw.discrepancy_amount ? `
        <div style="background:#fff1f2; border:1px solid #fecdd3; padding:8px 10px; border-radius:var(--radius-sm); font-size:12px; color:#9f1239;">
          <b>3-Way Match Discrepancy:</b> $${tw.discrepancy_amount.toFixed(2)}
        </div>
      ` : ''}
    </div>

    <div style="display:flex; flex-direction:column; gap:8px;">
      <button class="btn btn-primary" id="openDeepWorkbench">Open Full Review Workbench ↗</button>
      <div style="display:flex; gap:6px;">
        <button class="btn btn-secondary btn-sm" id="quickAssignMe" style="flex:1;">Assign to Me</button>
        <button class="btn btn-secondary btn-sm" id="quickEscalate" style="flex:1; color:var(--rose);">Escalate</button>
      </div>
    </div>
  `;

  $("#openDeepWorkbench").addEventListener("click", () => openWorkbench(item.id));
  $("#quickAssignMe").addEventListener("click", async () => {
    try {
      await patchCase(item.id, { assigned_to: "AP Controller", status: "IN_REVIEW" });
      await loadQueue();
      toast(`Assigned ${code} to AP Controller.`);
    } catch (err) { toast(err.message); }
  });
  $("#quickEscalate").addEventListener("click", async () => {
    try {
      await patchCase(item.id, { priority: "CRITICAL", status: "ESCALATED" });
      await loadQueue();
      toast(`Case ${code} escalated to Critical priority.`);
    } catch (err) { toast(err.message); }
  });
}

// Review Workbench Deep Inspector
async function openWorkbench(id) {
  try {
    const data = await getJson(`/api/cases/${id}`);
    state.currentWorkbenchCase = data;
    $("#navActiveCase").textContent = caseCode(data.id);
    renderWorkbench(data);
    setView("workbench");
  } catch (err) {
    toast(`Failed to load case: ${err.message}`);
  }
}

function renderWorkbench(item) {
  const container = $("#workbenchContainer");
  const invoice = item.invoice;
  const result = item.result;
  const po = result.matched_po;
  const tw = result.three_way_match || { lines: [] };
  const risk = result.risk_engine || { score: 0, level: "LOW", factors: [] };
  const dec = outcomeInfo(result.decision);
  const code = caseCode(item.id);
  const events = item.events || [];
  const corrections = item.corrections || {};

  // Build Three-Way Match Table Lines
  const linesHtml = (tw.lines || []).map(l => `
    <tr>
      <td style="font-family:var(--font-mono); font-weight:600;">${escapeHtml(l.sku || "—")}</td>
      <td>${escapeHtml(l.description || "—")}</td>
      <td class="num">${l.ordered_qty ?? "—"}</td>
      <td class="num">${l.received_qty ?? "—"}</td>
      <td class="num" style="font-weight:700;">${l.invoiced_qty ?? "—"}</td>
      <td class="num">${money(l.po_unit_price, invoice.currency)}</td>
      <td class="num" style="font-weight:700;">${money(l.invoiced_unit_price, invoice.currency)}</td>
      <td class="num" style="font-weight:700;">${money(l.line_total, invoice.currency)}</td>
      <td><span class="badge ${l.line_status === 'MATCH' ? 'badge-approve' : l.line_status === 'PARTIAL_RECEIPT' ? 'badge-approve' : 'badge-reject'}">${l.line_status}</span></td>
      <td style="font-size:11px; color:var(--text-dim);">${escapeHtml(l.status_detail || "")}</td>
    </tr>
  `).join("");

  // Build Risk Factors
  const factorsHtml = (risk.factors || []).map(f => `
    <div class="risk-factor-card">
      <div class="risk-factor-header">
        <b style="font-size:13px; color:var(--text-main);">${escapeHtml(f.title)}</b>
        <span class="factor-points-tag">+${f.points} pts</span>
      </div>
      <span class="risk-factor-why">${escapeHtml(f.why_it_matters)}</span>
      <div class="risk-factor-evidence"><b>Evidence:</b> ${escapeHtml(f.evidence)}</div>
      <div style="font-size:11px; color:var(--primary); font-weight:600; margin-top:2px;"><b>Action:</b> ${escapeHtml(f.recommendation)}</div>
    </div>
  `).join("");

  // Build Audit Events
  const eventsHtml = events.slice().reverse().map(e => `
    <div class="audit-event">
      <span class="event-dot event-${escapeHtml(e.kind)}"></span>
      <div class="event-info">
        <b>${escapeHtml(e.message)}</b>
        <small>${formatDate(e.created_at)}</small>
      </div>
    </div>
  `).join("");

  container.innerHTML = `
    <!-- Top Dossier Bar -->
    <div class="workbench-case-header">
      <div class="wb-title-wrap">
        <div class="overline">${code} · COMPREHENSIVE CASE WORKBENCH</div>
        <h2>${escapeHtml(invoice.vendor || "Supplier not identified")}</h2>
        <p>${escapeHtml(invoice.invoice_number || "No Invoice Reference")} · ${money(invoice.total, invoice.currency)} · Commitment: ${po ? po.po_number : 'None'}</p>
      </div>
      <div class="wb-header-badges">
        <span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.score ?? 0}/100 ${risk.level || 'LOW'} RISK</span>
        <span class="badge ${dec.class}">${dec.label}</span>
        <a class="btn btn-secondary btn-sm" href="/api/report/${item.id}" target="_blank" rel="noreferrer">Export Review Dossier ↓</a>
      </div>
    </div>

    <!-- Main Grid -->
    <div class="workbench-grid">
      <!-- Left Column: 3-Way Match & Risk Engine -->
      <div style="display:flex; flex-direction:column; gap:20px;">
        <!-- Three-Way Match Reconciliation -->
        <section class="wb-card">
          <div class="wb-card-head">
            <div>
              <b>Evidence-Backed Three-Way Invoice Match</b>
              <small>Line-by-line reconciliation of Invoice ↔ Purchase Order ↔ Goods Receipt (GRN)</small>
            </div>
            <span class="badge ${tw.status === 'MATCHED' ? 'badge-approve' : 'badge-review'}">${tw.status_label || 'Reconciled'}</span>
          </div>

          <div class="threeway-table-wrap">
            <table class="threeway-table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Description</th>
                  <th>PO Qty</th>
                  <th>GRN Qty</th>
                  <th>Inv Qty</th>
                  <th>PO Price</th>
                  <th>Inv Price</th>
                  <th>Total</th>
                  <th>Match Status</th>
                  <th>Discrepancy Detail</th>
                </tr>
              </thead>
              <tbody>
                ${linesHtml || '<tr><td colspan="10" style="text-align:center; color:var(--text-dim);">No line items available</td></tr>'}
              </tbody>
            </table>
          </div>

          ${tw.discrepancy_amount ? `
            <div style="padding:10px 14px; background:#fff1f2; border:1px solid #fecdd3; border-radius:var(--radius-md); display:flex; justify-content:space-between; align-items:center;">
              <span style="color:#9f1239; font-weight:700;">Financial Discrepancy Amount Identified:</span>
              <b style="font-family:var(--font-mono); color:#9f1239; font-size:15px;">$${tw.discrepancy_amount.toFixed(2)}</b>
            </div>
          ` : ''}
        </section>

        <!-- Explainable Risk Engine Signals -->
        <section class="wb-card">
          <div class="wb-card-head">
            <div>
              <b>Explainable Risk Engine (Score: ${risk.score ?? 0}/100)</b>
              <small>Mathematical factor breakdown and penalty contributions</small>
            </div>
            <span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.level || 'LOW'}</span>
          </div>

          <div class="risk-factor-list">
            ${factorsHtml || '<div style="color:var(--text-dim); font-size:12px; padding:8px;">Zero risk factors triggered. Clean match across all internal controls.</div>'}
          </div>
        </section>

        <!-- AI Review Assistant -->
        <section class="wb-card ai-assistant-card">
          <div class="ai-assistant-head">
            <span class="ai-avatar">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10H12V2z"></path><path d="M12 12 2.1 12.5"></path><path d="m4.5 15 7.5-3"></path><path d="m15 4.5-3 7.5"></path></svg>
            </span>
            <div>
              <b style="font-size:14px; color:#1e1b4b;">AI Accounts Payable Assistant</b>
              <small style="color:#6366f1;">Grounded strictly in verified invoice, PO, and GRN evidence</small>
            </div>
          </div>

          <div class="ai-chips-row">
            <button class="ai-prompt-chip" data-query="Why was this invoice flagged?">Why was this invoice flagged?</button>
            <button class="ai-prompt-chip" data-query="Which fields do not match the PO or GRN?">Which fields do not match the PO/GRN?</button>
            <button class="ai-prompt-chip" data-query="What should the reviewer do next?">What should the reviewer do next?</button>
            <button class="ai-prompt-chip" data-query="Summarize this invoice">Summarize this invoice</button>
          </div>

          <div class="ai-chat-thread" id="aiChatThread">
            <div class="ai-message assistant">
              <b>Mosaic AI Assistant:</b> Hello! I have evaluated Case ${code} against Purchase Order ${po ? po.po_number : 'records'} and verified receiving data. Click a prompt above or type a question to inspect discrepancies.
            </div>
          </div>

          <form class="ai-input-form" id="aiInputForm">
            <input id="aiQuestionInput" type="text" placeholder="Ask about PO variance, receiving quantities, taxes, supplier…">
            <button type="submit" class="btn btn-primary btn-sm">Ask Assistant</button>
          </form>
        </section>
      </div>

      <!-- Right Column: Governance, Corrections, Audit -->
      <div style="display:flex; flex-direction:column; gap:20px;">
        <!-- Reviewer Disposition & Workflow -->
        <section class="wb-card">
          <div class="wb-card-head">
            <b>Reviewer Governance & Disposition</b>
            <small>Override requires mandatory audit rationale</small>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label for="wbStatus">Workflow State</label>
              <select id="wbStatus">
                <option value="NEW" ${item.status === 'NEW' ? 'selected' : ''}>New</option>
                <option value="IN_REVIEW" ${item.status === 'IN_REVIEW' ? 'selected' : ''}>In Review</option>
                <option value="WAITING" ${item.status === 'WAITING' ? 'selected' : ''}>Waiting on Procurement</option>
                <option value="ESCALATED" ${item.status === 'ESCALATED' ? 'selected' : ''}>Escalated</option>
                <option value="RESOLVED" ${item.status === 'RESOLVED' ? 'selected' : ''}>Resolved</option>
              </select>
            </div>

            <div class="form-group">
              <label for="wbPriority">Case Priority</label>
              <select id="wbPriority">
                <option value="LOW" ${(item.priority || 'MEDIUM') === 'LOW' ? 'selected' : ''}>Low</option>
                <option value="MEDIUM" ${(item.priority || 'MEDIUM') === 'MEDIUM' ? 'selected' : ''}>Medium</option>
                <option value="HIGH" ${(item.priority || 'MEDIUM') === 'HIGH' ? 'selected' : ''}>High</option>
                <option value="CRITICAL" ${(item.priority || 'MEDIUM') === 'CRITICAL' ? 'selected' : ''}>Critical</option>
              </select>
            </div>

            <div class="form-group" style="grid-column:1/-1;">
              <label for="wbAssignee">Assigned Reviewer</label>
              <input id="wbAssignee" value="${escapeHtml(item.assigned_to || '')}" placeholder="e.g. AP Specialist, Senior Controller">
            </div>

            <div class="form-group" style="grid-column:1/-1;">
              <label for="wbOverride">Reviewer Disposition (Override Model)</label>
              <select id="wbOverride">
                <option value="">Keep Model Recommendation (${result.decision})</option>
                <option value="APPROVE" ${item.decision_override === 'APPROVE' ? 'selected' : ''}>Approve (Override to Clearance)</option>
                <option value="REVIEW" ${item.decision_override === 'REVIEW' ? 'selected' : ''}>Review (Hold for Clarification)</option>
                <option value="REJECT" ${item.decision_override === 'REJECT' ? 'selected' : ''}>Reject (Stop / Void Invoice)</option>
              </select>
            </div>

            <div class="form-group" style="grid-column:1/-1;">
              <label for="wbRationale">Override Justification Rationale</label>
              <input id="wbRationale" value="${escapeHtml(item.override_rationale || '')}" placeholder="Required when overriding the automated model recommendation">
            </div>
          </div>

          <button class="btn btn-primary" id="saveGovernanceBtn" style="margin-top:6px;">Save Workflow & Disposition</button>
        </section>

        <!-- Extraction Feedback & Corrections -->
        <section class="wb-card">
          <div class="wb-card-head">
            <b>Extraction Feedback & Human Correction</b>
            <small>Field corrections retain original extracted values for model evaluation</small>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label for="corrField">Field</label>
              <select id="corrField">
                <option value="total">Invoice Total</option>
                <option value="subtotal">Subtotal</option>
                <option value="tax">Tax</option>
                <option value="invoice_number">Invoice Number</option>
                <option value="invoice_date">Invoice Date</option>
                <option value="vendor">Supplier Name</option>
                <option value="po_number">PO Reference</option>
              </select>
            </div>

            <div class="form-group">
              <label for="corrValue">Corrected Value</label>
              <input id="corrValue" placeholder="Verified true value">
            </div>

            <div class="form-group" style="grid-column:1/-1;">
              <label for="corrReason">Correction Reason</label>
              <input id="corrReason" placeholder="e.g. OCR misread dollar symbol; confirmed from supplier remittance">
            </div>
          </div>

          <button class="btn btn-secondary btn-sm" id="saveCorrectionBtn">Save Field Correction</button>

          <!-- Existing Corrections List -->
          <div id="correctionsList" style="margin-top:8px;">
            ${Object.entries(corrections).map(([f, c]) => `
              <div style="font-size:11.5px; background:var(--bg-surface); padding:6px 10px; border-radius:var(--radius-sm); margin-top:4px;">
                <b>${escapeHtml(f)}:</b> ${escapeHtml(c.original)} → <span style="color:var(--primary); font-weight:700;">${escapeHtml(c.corrected)}</span>
                <small style="display:block; color:var(--text-dim);">${escapeHtml(c.rationale)}</small>
              </div>
            `).join("")}
          </div>
        </section>

        <!-- Reviewer Notes & Audit Trail -->
        <section class="wb-card">
          <div class="wb-card-head">
            <b>Reviewer Notes & Activity Trail</b>
            <small>Immutable compliance history</small>
          </div>

          <div class="form-group">
            <textarea id="caseNote" placeholder="Add follow-up notes, procurement inquiries, or resolution explanation…"></textarea>
            <button class="btn btn-secondary btn-sm" id="addNoteBtn" style="align-self:flex-start; margin-top:4px;">Add Audited Note</button>
          </div>

          <div class="audit-timeline" style="margin-top:14px; max-height:220px; overflow-y:auto;">
            ${eventsHtml || '<div style="color:var(--text-dim); font-size:12px;">No activity recorded yet.</div>'}
          </div>
        </section>
      </div>
    </div>
  `;

  // Attach Workbench Listeners
  $("#saveGovernanceBtn").addEventListener("click", async () => {
    try {
      const status = $("#wbStatus").value;
      const priority = $("#wbPriority").value;
      const assigned_to = $("#wbAssignee").value;
      const decision_override = $("#wbOverride").value;
      const override_rationale = $("#wbRationale").value;

      const updated = await patchCase(item.id, {
        status, priority, assigned_to, decision_override, override_rationale
      });
      state.currentWorkbenchCase = updated;
      renderWorkbench(updated);
      await loadQueue();
      toast("Governance workflow & disposition recorded.");
    } catch (err) { toast(err.message); }
  });

  $("#saveCorrectionBtn").addEventListener("click", async () => {
    const field = $("#corrField").value;
    const value = $("#corrValue").value.trim();
    const rationale = $("#corrReason").value.trim();

    if (!value || !rationale) {
      toast("Please provide both corrected value and reason.");
      return;
    }
    try {
      const updated = await patchCase(item.id, {
        correction: {
          field,
          value: ["total", "subtotal", "tax"].includes(field) ? Number(value) : value,
          rationale
        }
      });
      state.currentWorkbenchCase = updated;
      renderWorkbench(updated);
      toast("Field correction recorded as evaluation feedback.");
    } catch (err) { toast(err.message); }
  });

  $("#addNoteBtn").addEventListener("click", async () => {
    const note = $("#caseNote").value.trim();
    if (!note) return;
    try {
      const updated = await patchCase(item.id, { note });
      state.currentWorkbenchCase = updated;
      renderWorkbench(updated);
      toast("Audited note added to activity trail.");
    } catch (err) { toast(err.message); }
  });

  // AI Assistant Interaction
  $$(".ai-prompt-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.query;
      $("#aiQuestionInput").value = q;
      triggerAiQuery(item.id, q);
    });
  });

  $("#aiInputForm").addEventListener("submit", e => {
    e.preventDefault();
    const q = $("#aiQuestionInput").value.trim();
    if (q) triggerAiQuery(item.id, q);
  });
}

async function triggerAiQuery(caseId, query) {
  const thread = $("#aiChatThread");
  thread.innerHTML += `<div class="ai-message user"><b>You:</b> ${escapeHtml(query)}</div>`;
  thread.scrollTop = thread.scrollHeight;
  $("#aiQuestionInput").value = "";

  try {
    const res = await fetch("/api/assistant", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Session-ID": getSessionId()
      },
      body: JSON.stringify({ case_id: caseId, query })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Assistant query failed");

    // Convert simple markdown headings & lists for rendering
    let htmlAnswer = escapeHtml(data.answer)
      .replace(/### (.*?)\n/g, '<h4 style="font-size:13px; font-weight:700; margin:4px 0;">$1</h4>')
      .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
      .replace(/`([^`]+)`/g, '<code style="background:var(--bg-surface); padding:2px 4px; border-radius:3px; font-family:var(--font-mono); font-size:11px;">$1</code>')
      .replace(/\n\n/g, '<br><br>');

    thread.innerHTML += `
      <div class="ai-message assistant">
        <b>Mosaic AI Assistant:</b><br>${htmlAnswer}
        ${(data.citations || []).length ? `
          <div style="margin-top:8px; padding-top:6px; border-top:1px dashed var(--border-light); font-size:11px; color:var(--text-dim);">
            <b>Evidence Citations:</b> ${data.citations.map(c => `${c.field}: “${c.value}”`).join(" · ")}
          </div>
        ` : ''}
      </div>
    `;
    thread.scrollTop = thread.scrollHeight;
  } catch (err) {
    thread.innerHTML += `<div class="ai-message assistant" style="color:var(--rose);">Assistant error: ${escapeHtml(err.message)}</div>`;
  }
}

async function patchCase(id, changes) {
  const response = await fetch(`/api/cases/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Session-ID": getSessionId()
    },
    body: JSON.stringify(changes)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The case update could not be saved.");
  return data;
}

// Vendor Intelligence
async function renderVendors() {
  const grid = $("#vendorGrid");
  const query = $("#vendorSearch")?.value.trim().toLowerCase() || "";
  const filterStatus = $("#vendorFilterStatus")?.value || "";
  const filterRisk = $("#vendorFilterRisk")?.value || "";

  state.vendors = await getJson("/api/vendors");

  const totalSpend = state.vendors.reduce((s, v) => s + (v.metrics?.total_invoiced_amount || 0), 0);
  const flaggedCount = state.vendors.filter(v => v.verification_status !== "VERIFIED").length;

  $("#vStatCount").textContent = state.vendors.length;
  $("#vStatSpend").textContent = money(totalSpend, "USD");
  $("#vStatFlagged").textContent = flaggedCount;

  const filtered = state.vendors.filter(v => {
    if (filterStatus && v.verification_status !== filterStatus) return false;
    if (filterRisk && v.risk_rating !== filterRisk) return false;
    if (query) {
      const hay = `${v.name} ${v.category} ${v.tax_id} ${v.vendor_id}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  if (!filtered.length) {
    grid.innerHTML = "<div class='recent-empty'>No vendor profiles match this filter.</div>";
    return;
  }

  grid.innerHTML = filtered.map(v => {
    const bank = v.bank_details || {};
    const metrics = v.metrics || {};
    const isVerified = v.verification_status === "VERIFIED";

    return `
      <div class="vendor-card">
        <div class="vendor-card-head">
          <div>
            <b>${escapeHtml(v.name)}</b>
            <small>${escapeHtml(v.category)} · Tax ID: ${escapeHtml(v.tax_id)}</small>
          </div>
          <span class="risk-tag ${riskBadgeClass(v.risk_rating)}">${escapeHtml(v.risk_rating)} RISK</span>
        </div>

        <div class="bank-detail-box">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <small>Remittance & Banking</small>
            <span class="badge ${isVerified ? 'badge-approve' : 'badge-reject'}" style="font-size:10px;">${escapeHtml(v.verification_status)}</span>
          </div>
          <b>${escapeHtml(bank.bank_name || 'Standard Remit')}</b>
          <span style="font-size:11.5px; color:var(--text-dim); font-family:var(--font-mono);">Acct: ****${escapeHtml(bank.account_number_last4 || '----')} · Routing: ${escapeHtml(bank.routing_number || '----')}</span>
        </div>

        ${!isVerified ? `
          <div style="background:#fee2e2; border:1px solid #fecaca; border-radius:var(--radius-sm); padding:6px 10px; font-size:11.5px; color:#991b1b;">
            <b>Flagged:</b> Bank account unverified on procurement master. Out-of-band verification required.
          </div>
        ` : ''}

        <div class="vendor-stats-strip">
          <div class="vendor-stat-cell"><small>Lifetime Spend</small><b>${money(metrics.total_invoiced_amount, "USD")}</b></div>
          <div class="vendor-stat-cell"><small>Invoices</small><b>${metrics.invoice_count ?? 0}</b></div>
          <div class="vendor-stat-cell"><small>Exception Rate</small><b>${metrics.exception_rate_pct ?? 0}%</b></div>
        </div>

        <div style="font-size:11.5px; color:var(--text-muted); line-height:1.4;">
          ${escapeHtml(v.notes || "")}
        </div>
      </div>
    `;
  }).join("");
}

// Case History
async function loadRuns() {
  const req = ++state.historyRequest;
  const params = new URLSearchParams({ limit: "1000" });
  if (state.filter) params.set("status", state.filter);
  if (state.search) params.set("q", state.search);

  const runs = await getJson(`/api/runs?${params}`);
  if (req !== state.historyRequest) return;
  state.runs = runs;

  const tbody = $("#archiveRows");
  if (!runs.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-table">No historical records match your search query.</td></tr>`;
    $("#archiveDetail").innerHTML = `<div class="detail-empty"><b>No case selected.</b></div>`;
    return;
  }

  tbody.innerHTML = runs.map(r => {
    const dec = outcomeInfo(r.result.decision);
    const risk = r.result.risk_engine || { score: 0, level: "LOW" };

    return `
      <tr data-run-id="${r.id}">
        <td style="font-family:var(--font-mono); font-weight:700;">${caseCode(r.id)}</td>
        <td style="font-weight:600;">${escapeHtml(r.invoice.vendor || "Unknown")}</td>
        <td style="font-family:var(--font-mono);">${escapeHtml(r.invoice.invoice_number || "—")}</td>
        <td style="font-family:var(--font-mono);">${escapeHtml(r.result.matched_po?.po_number || r.invoice.po_number || "—")}</td>
        <td style="font-family:var(--font-mono); font-weight:600;">${money(r.invoice.total, r.invoice.currency)}</td>
        <td><span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.score ?? 0}</span></td>
        <td><span class="badge ${dec.class}">${dec.label}</span></td>
        <td style="font-size:11.5px; color:var(--text-dim);">${formatDate(r.created_at)}</td>
        <td>
          <a class="btn btn-secondary btn-sm" href="/api/report/${r.id}" target="_blank" rel="noreferrer" title="Open PDF / Print Dossier">Dossier ↗</a>
        </td>
      </tr>
    `;
  }).join("");

  $$("#archiveRows tr[data-run-id]").forEach(tr => {
    tr.addEventListener("click", () => openArchiveDetail(Number(tr.dataset.runId)));
  });

  if (runs[0]) openArchiveDetail(runs[0].id);
}

function openArchiveDetail(id) {
  const run = state.runs.find(r => r.id === id);
  if (!run) return;

  $$("#archiveRows tr").forEach(tr => tr.classList.toggle("selected", Number(tr.dataset.runId) === id));

  const invoice = run.invoice;
  const result = run.result;
  const dec = outcomeInfo(result.decision);
  const risk = result.risk_engine || {};

  $("#archiveDetail").innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div>
        <b style="font-size:15px; color:var(--text-main);">${caseCode(run.id)}: ${escapeHtml(invoice.vendor || "Supplier not identified")}</b>
        <span style="font-size:12px; color:var(--text-dim); margin-left:8px;">${money(invoice.total, invoice.currency)}</span>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary btn-sm" id="loadIntoWorkbenchBtn">Open in Workbench ↗</button>
        <button class="btn btn-secondary btn-sm" id="downloadPacketBtn">Download Case JSON ↓</button>
      </div>
    </div>
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:12px;">
      <div class="field-cell"><small>Model Decision</small><b>${dec.label}</b></div>
      <div class="field-cell"><small>Risk Rating</small><b>${risk.score ?? 0}/100 (${risk.level || 'LOW'})</b></div>
      <div class="field-cell"><small>Workflow Status</small><b>${(run.status || 'NEW').replace('_', ' ')}</b></div>
      <div class="field-cell"><small>Assigned Reviewer</small><b>${escapeHtml(run.assigned_to || 'Unassigned')}</b></div>
    </div>
    <div style="background:var(--bg-surface); padding:10px 14px; border-radius:var(--radius-md); font-size:12.5px; color:var(--text-main); line-height:1.45;">
      <b>Verification Rationale:</b> ${escapeHtml(result.reason || "Controls passed.")}<br>
      <b>Next Step Guidance:</b> ${escapeHtml(result.next_step || "Standard approval flow.")}
    </div>
  `;

  $("#loadIntoWorkbenchBtn").addEventListener("click", () => openWorkbench(run.id));
  $("#downloadPacketBtn").addEventListener("click", () => downloadJson(run, `mosaic-case-${run.id}.json`));
}

// Analytics Dashboard Rendering
function renderAnalytics(summary) {
  $("#statTotal").textContent = summary.total ?? 0;
  $("#statInvoicedValue").textContent = money(summary.total_invoiced_value, "USD");
  $("#statPendingValue").textContent = money(summary.pending_review_value, "USD");
  $("#statDiscrepancies").textContent = money(summary.discrepancies_amount, "USD");
  $("#statDuplicates").textContent = summary.duplicates_detected ?? 0;
  $("#statReview").textContent = summary.review ?? 0;

  // Render 7-day Activity Chart
  const days = summary.daily || [];
  const maxDay = Math.max(1, ...days.map(d => d.total));
  $("#activityTotal").textContent = `${days.reduce((s, d) => s + d.total, 0)} cases in 7-day window`;

  $("#activityChart").innerHTML = days.map(day => {
    const dateObj = new Date(`${day.date}T12:00:00Z`);
    const dayLabel = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" }).format(dateObj);
    const height = Math.max(4, Math.round((day.total / maxDay) * 80));

    return `
      <div class="activity-day" title="${day.date}: ${day.total} cases (${money(day.value, 'USD')})">
        <div class="activity-bars">
          <div class="activity-bar approve" style="height: ${day.total ? Math.round(height * (day.approved / day.total)) : 0}px;"></div>
          <div class="activity-bar review" style="height: ${day.total ? Math.round(height * (day.review / day.total)) : 0}px;"></div>
          <div class="activity-bar reject" style="height: ${day.total ? Math.round(height * (day.rejected / day.total)) : 0}px;"></div>
        </div>
        <small style="font-family:var(--font-mono); font-size:10px; color:var(--text-dim);">${dayLabel}</small>
      </div>
    `;
  }).join("");

  // Exception Distribution
  const dist = summary.exception_distribution || {};
  const distTotal = Math.max(1, Object.values(dist).reduce((a, b) => a + b, 0));
  $("#exceptionDistChart").innerHTML = Object.entries(dist).map(([cat, count]) => {
    const pct = Math.round((count / distTotal) * 100);
    return `
      <div class="dist-row">
        <div class="dist-labels">
          <span style="font-weight:600; color:var(--text-main);">${escapeHtml(cat)}</span>
          <span style="font-family:var(--font-mono); color:var(--text-dim);">${count} (${pct}%)</span>
        </div>
        <div class="dist-bar-wrap">
          <div class="dist-bar-fill" style="width: ${pct}%;"></div>
        </div>
      </div>
    `;
  }).join("");

  // Vendor Spend Concentration
  const spendList = summary.vendor_spending || [];
  $("#vendorSpendTable").innerHTML = spendList.map(item => `
    <div class="spend-row">
      <b style="color:var(--text-main);">${escapeHtml(item.vendor)}</b>
      <span style="font-family:var(--font-mono); font-weight:700; color:var(--primary);">${money(item.amount, "USD")}</span>
      <span class="badge badge-approve" style="justify-self:flex-start;">Active Commitment</span>
    </div>
  `).join("") || "<div class='recent-empty'>No vendor spend data available.</div>";
}

// How It Works Policy Cases
function renderPolicyCases() {
  const container = $("#policyCases");
  container.innerHTML = state.samples.map(s => `
    <div class="demo-case" data-file="${escapeHtml(s.file)}">
      <b>${escapeHtml(s.title)}</b>
      <small>${escapeHtml(s.note)}</small>
      <em style="color: ${s.kind === 'approve' ? 'var(--green)' : s.kind === 'stop' ? 'var(--rose)' : 'var(--amber)'};">
        ${s.kind === 'approve' ? 'CLEAN CLEARANCE' : s.kind === 'stop' ? 'FRAUD / DUPLICATE STOP' : 'EXCEPTION REVIEW'}
      </em>
    </div>
  `).join("");

  $$(".demo-case", container).forEach(card => {
    card.addEventListener("click", () => {
      setSelected(card.dataset.file);
      setView("desk");
      window.scrollTo({ top: $("#intake-body")?.offsetTop || 200, behavior: "smooth" });
      toast(`Loaded scenario: ${card.querySelector("b").textContent}`);
    });
  });
}

// Notification Center
async function checkNotifications() {
  try {
    const data = await getJson("/api/notifications");
    state.notifications = data;
    const badge = $("#notificationCount");
    badge.textContent = data.unread_count;
    badge.hidden = !data.unread_count;
    $("#notificationSubtitle").textContent = `${data.unread_count} pending alerts requiring triage`;

    const list = $("#notificationList");
    const items = [
      ...data.critical_cases.map(c => `
        <div class="notification-item" data-case-id="${c.id}">
          <span class="notification-dot critical"></span>
          <div class="notification-content">
            <b>Critical Risk Exception #${c.id}</b>
            <p>${escapeHtml(c.vendor)}: ${escapeHtml(c.reason)}</p>
          </div>
        </div>
      `),
      ...data.unassigned_cases.map(c => `
        <div class="notification-item" data-case-id="${c.id}">
          <span class="notification-dot unassigned"></span>
          <div class="notification-content">
            <b>Unassigned Review #${c.id}</b>
            <p>${escapeHtml(c.vendor)} · ${money(c.amount)} awaiting assignment</p>
          </div>
        </div>
      `)
    ];

    list.innerHTML = items.length ? items.join("") : "<div class='notification-empty'>No alerts pending review.</div>";

    $$(".notification-item", list).forEach(item => {
      item.addEventListener("click", () => {
        $("#notificationPopover").hidden = true;
        openWorkbench(Number(item.dataset.caseId));
      });
    });
  } catch {
    /* Silent notification check failure */
  }
}

// Global Command Menu (Ctrl+K)
const commands = [
  { icon: "◫", title: "Review Desk", detail: "Start or continue an invoice review", run: () => setView("desk") },
  { icon: "▤", title: "Exception Queue", detail: "Prioritize, triage, and assign cases", run: () => setView("queue") },
  { icon: "▣", title: "Review Workbench", detail: "Open 3-way match, risk, and AI assistant", run: () => setView("workbench") },
  { icon: "👥", title: "Vendor Intelligence", detail: "View vendor directory & bank verification", run: () => setView("vendors") },
  { icon: "↗", title: "Case History Archive", detail: "Search past decisions and export CSV", run: () => setView("history") },
  { icon: "▥", title: "Analytics Dashboard", detail: "Inspect volume, spend, and discrepancies", run: () => setView("analytics") },
  { icon: "ⓘ", title: "How It Works", detail: "Inspect internal controls & pipeline", run: () => setView("policy") },
  { icon: "✳", title: "Clean 3-Way Match Scenario", detail: "Load exact-matching happy path scenario", run: () => { setView("desk"); setSelected("happy_path.pdf"); } },
  { icon: "⚠", title: "3-Way Quantity Mismatch Scenario", detail: "Load quantity exceeding GRN scenario", run: () => { setView("desk"); setSelected("quantity_mismatch.pdf"); } },
  { icon: "⛔", title: "Duplicate Submission Scenario", detail: "Load cryptographic duplicate scenario", run: () => { setView("desk"); setSelected("duplicate_invoice.pdf"); } },
  { icon: "↑", title: "Upload Custom PDF Invoice", detail: "Open local file picker", run: () => { setView("desk"); $("#tabUpload").click(); $("#invoiceFile").click(); } },
  { icon: "📋", title: "PO Commitments Register", detail: "Open purchase orders register modal", run: () => { $("#modalBackdrop").hidden = false; } },
  { icon: "↺", title: "Clear Workspace (Clean Slate)", detail: "Reset to 0 cases so you can review invoices from scratch", run: resetWorkspaceSession },
  { icon: "📥", title: "Load Sample Dataset", detail: "Pre-populate 3 active exceptions & 3 history cases", run: loadDemoDataset }
];

function showCommandMenu() {
  $("#commandBackdrop").hidden = false;
  $("#commandSearch").value = "";
  state.commandIndex = 0;
  renderCommandResults();
  $("#commandSearch").focus();
}

function hideCommandMenu() {
  $("#commandBackdrop").hidden = true;
}

function renderCommandResults() {
  const query = $("#commandSearch").value.trim().toLowerCase();
  const filtered = commands.filter(c => `${c.title} ${c.detail}`.toLowerCase().includes(query));
  state.visibleCommands = filtered;
  state.commandIndex = Math.min(state.commandIndex, Math.max(0, filtered.length - 1));

  const results = $("#commandResults");
  results.innerHTML = filtered.length ? filtered.map((c, i) => `
    <div class="command-option ${i === state.commandIndex ? "active" : ""}" data-index="${i}">
      <span style="font-size:16px;">${c.icon}</span>
      <div>
        <b>${escapeHtml(c.title)}</b>
        <small>${escapeHtml(c.detail)}</small>
      </div>
      ${i === state.commandIndex ? "<kbd style='margin-left:auto; font-size:10px;'>ENTER</kbd>" : ""}
    </div>
  `).join("") : "<div class='command-empty'>No matching actions found.</div>";

  $$(".command-option", results).forEach(opt => {
    opt.addEventListener("click", () => runCommand(Number(opt.dataset.index)));
  });
}

function runCommand(index) {
  const cmd = state.visibleCommands?.[index];
  if (!cmd) return;
  hideCommandMenu();
  cmd.run();
}

function renderSummary(summary) {
  $("#statTotal").textContent = summary.total ?? 0;
  $("#statInvoicedValue").textContent = money(summary.total_invoiced_value, "USD");
  $("#statPendingValue").textContent = money(summary.pending_review_value, "USD");
  $("#statDiscrepancies").textContent = money(summary.discrepancies_amount, "USD");
  $("#statDuplicates").textContent = summary.duplicates_detected ?? 0;
  $("#navOpen").textContent = summary.review ?? 0;
  $("#navOpen").hidden = !summary.review;
  $("#navQueue").textContent = summary.open_cases ?? 0;
  $("#navQueue").hidden = !summary.open_cases;

  const recent = summary.recent || [];
  $("#recentList").innerHTML = recent.length ? recent.map(r => {
    const inv = r.invoice;
    const dec = outcomeInfo(r.result.decision);
    const risk = r.result.risk_engine || { score: 0, level: "LOW" };
    const prio = r.priority || "MEDIUM";

    return `
      <div class="recent-row" data-run-id="${r.id}">
        <span class="recent-case">${caseCode(r.id)}</span>
        <span class="recent-supplier">${escapeHtml(inv.vendor || "Supplier not identified")}</span>
        <span class="recent-invoice">${escapeHtml(inv.invoice_number || "No Ref")}</span>
        <span class="recent-amount">${money(inv.total, inv.currency)}</span>
        <div><span class="risk-tag ${riskBadgeClass(risk.level)}">${risk.score ?? 0}</span></div>
        <div><span class="badge ${dec.class}">${dec.label}</span></div>
        <div><span class="workflow-chip workflow-${(r.status || 'NEW').toLowerCase()}">${(r.status || 'NEW').replace('_', ' ')}</span></div>
      </div>
    `;
  }).join("") : "<div class='recent-empty'>Reviewed invoices will appear here.</div>";

  $$(".recent-row[data-run-id]").forEach(row => {
    row.addEventListener("click", () => openWorkbench(Number(row.dataset.runId)));
  });
}

function renderPos() {
  $("#poCount").textContent = state.pos.length;
  $("#poModalTable").innerHTML = state.pos.map(po => `
    <div class="po-row">
      <b style="font-family:var(--font-mono); color:var(--primary);">${escapeHtml(po.po_number)}</b>
      <div>
        <b style="color:var(--text-main); font-size:13px;">${escapeHtml(po.vendor)}</b>
        <small style="display:block; color:var(--text-dim); font-size:11px;">${escapeHtml(po.description || "")}</small>
      </div>
      <b style="font-family:var(--font-mono);">${money(po.approved_amount, po.currency)}</b>
      <div><span class="badge ${po.status === 'approved' ? 'badge-approve' : 'badge-review'}">${po.status.toUpperCase()}</span></div>
    </div>
  `).join("");
}

function setTolerance(val) {
  state.tolerance = Math.max(0, Math.min(10, Number(val) || 0));
  $("#tolerance").value = state.tolerance;
  $("#toleranceValue").textContent = `${state.tolerance.toFixed(1)}%`;
  try { localStorage.setItem("mosaic.tolerance", String(state.tolerance)); } catch {}
}

async function loadWorkspace() {
  try {
    const [samples, pos, summary, vendors] = await Promise.all([
      getJson("/api/samples"),
      getJson("/api/pos"),
      getJson("/api/summary"),
      getJson("/api/vendors")
    ]);
    state.samples = samples;
    state.pos = pos;
    state.vendors = vendors;

    renderScenarios();
    renderPos();
    renderPolicyCases();
    renderSummary(summary);
    renderAnalytics(summary);
    renderVendors();
    await loadQueue().catch(() => {});
    await checkNotifications();

    // Default select clean match
    if (samples.length && !state.selected) {
      setSelected(samples[0].file);
    }
  } catch (err) {
    toast(`Failed to load workspace data: ${err.message}`);
  }
}

// Global Initialization
function init() {
  $("#today").textContent = new Intl.DateTimeFormat("en-US", {
    weekday: "short", month: "short", day: "numeric"
  }).format(new Date());

  try { setTolerance(localStorage.getItem("mosaic.tolerance") ?? 2.0); } catch { setTolerance(2.0); }

  $("#runButton").addEventListener("click", runReview);
  $("#tolerance").addEventListener("input", e => setTolerance(e.target.value));

  // Intake tabs
  $("#tabScenarios").addEventListener("click", () => {
    $("#tabScenarios").classList.add("active");
    $("#tabUpload").classList.remove("active");
    $("#scenarioPanel").hidden = false;
    $("#uploadPanel").hidden = true;
  });
  $("#tabUpload").addEventListener("click", () => {
    $("#tabUpload").classList.add("active");
    $("#tabScenarios").classList.remove("active");
    $("#scenarioPanel").hidden = true;
    $("#uploadPanel").hidden = false;
  });

  // Navigation clicks
  $$(".nav-item").forEach(btn => btn.addEventListener("click", () => setView(btn.dataset.view)));
  $$("[data-goto]").forEach(btn => btn.addEventListener("click", () => setView(btn.dataset.goto)));

  // PO Register modal
  $("#viewPO").addEventListener("click", () => { $("#modalBackdrop").hidden = false; });
  $("#modalClose").addEventListener("click", () => { $("#modalBackdrop").hidden = true; });
  $("#closePoModal").addEventListener("click", () => { $("#modalBackdrop").hidden = true; });
  $("#modalBackdrop").addEventListener("click", e => { if (e.target.id === "modalBackdrop") e.currentTarget.hidden = true; });

  // Reset demo session & load dataset
  $("#btnResetDemo")?.addEventListener("click", resetWorkspaceSession);
  $("#btnSeedDemo")?.addEventListener("click", loadDemoDataset);

  // Notifications Popover Toggle
  $("#notificationTrigger").addEventListener("click", e => {
    e.stopPropagation();
    const pop = $("#notificationPopover");
    pop.hidden = !pop.hidden;
  });
  document.addEventListener("click", e => {
    if (!$("#notificationPopover").contains(e.target) && e.target !== $("#notificationTrigger")) {
      $("#notificationPopover").hidden = true;
    }
  });

  // Global search button
  $("#globalSearchBtn").addEventListener("click", showCommandMenu);
  $("#helpButton").addEventListener("click", showCommandMenu);

  // Command palette events
  $("#commandSearch").addEventListener("input", () => {
    state.commandIndex = 0;
    renderCommandResults();
  });
  $("#commandBackdrop").addEventListener("click", e => { if (e.target.id === "commandBackdrop") hideCommandMenu(); });
  $("#commandBackdrop").addEventListener("keydown", e => {
    const count = state.visibleCommands?.length || 0;
    if (e.key === "ArrowDown" && count) { e.preventDefault(); state.commandIndex = (state.commandIndex + 1) % count; renderCommandResults(); }
    if (e.key === "ArrowUp" && count) { e.preventDefault(); state.commandIndex = (state.commandIndex - 1 + count) % count; renderCommandResults(); }
    if (e.key === "Enter") { e.preventDefault(); runCommand(state.commandIndex); }
  });

  // Keyboard navigation
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      showCommandMenu();
    }
    if (e.key === "Escape") {
      hideCommandMenu();
      $("#modalBackdrop").hidden = true;
      $("#notificationPopover").hidden = true;
    }
    // Queue shortcuts
    if (!["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && $("#view-queue").classList.contains("active")) {
      const rows = $$(".queue-row");
      const current = rows.findIndex(r => Number(r.dataset.caseId) === state.currentQueueCase?.id);
      if (["j", "k"].includes(e.key.toLowerCase()) && rows.length) {
        e.preventDefault();
        const nextIdx = (current + (e.key.toLowerCase() === "j" ? 1 : -1) + rows.length) % rows.length;
        rows[nextIdx].click();
      } else if (e.key === "Enter" && state.currentQueueCase) {
        e.preventDefault();
        openWorkbench(state.currentQueueCase.id);
      }
    }
  });

  // File Upload handling
  $("#invoiceFile").addEventListener("change", e => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      toast("Please upload a PDF invoice.");
      e.target.value = "";
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      toast("PDF exceeds 15 MB demo limit.");
      e.target.value = "";
      return;
    }
    state.file = file;
    state.selected = null;
    renderScenarios();
    $("#filePill").hidden = false;
    $("#filePill").textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    $("#uploadTitle").textContent = "PDF Uploaded & Ready";
    $("#uploadHelp").textContent = "Click 'Review Invoice' to run automated controls.";
    refreshRunButton();
    toast(`Loaded ${file.name}. Ready to review.`);
  });

  const dropzone = $("#dropzone");
  dropzone.addEventListener("click", () => $("#invoiceFile").click());
  ["dragenter", "dragover"].forEach(n => dropzone.addEventListener(n, e => { e.preventDefault(); dropzone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(n => dropzone.addEventListener(n, e => { e.preventDefault(); dropzone.classList.remove("dragover"); }));
  dropzone.addEventListener("drop", e => {
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    const input = $("#invoiceFile");
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  // Queue Filters
  $("#queueStatus").addEventListener("change", renderQueue);
  $("#queueDecision").addEventListener("change", renderQueue);
  $("#queuePriority")?.addEventListener("change", renderQueue);
  $("#queueSearch").addEventListener("input", renderQueue);

  // Vendor Filters
  $("#vendorSearch")?.addEventListener("input", renderVendors);
  $("#vendorFilterStatus")?.addEventListener("change", renderVendors);
  $("#vendorFilterRisk")?.addEventListener("change", renderVendors);

  // History Filters & CSV Export
  $("#searchRuns").addEventListener("input", e => {
    state.search = e.target.value;
    clearTimeout(init.searchTimer);
    init.searchTimer = setTimeout(() => loadRuns().catch(err => toast(err.message)), 220);
  });
  $("#filterRuns").addEventListener("change", e => {
    state.filter = e.target.value;
    loadRuns().catch(err => toast(err.message));
  });

  $("#exportRuns").addEventListener("click", async () => {
    try {
      const runs = await getJson("/api/runs?limit=1000");
      const rows = [
        ["Case ID", "Supplier", "Invoice Ref", "PO Commitment", "Amount", "Currency", "Risk Score", "Risk Level", "Outcome", "Status", "Priority", "Assigned To", "Reviewed At"],
        ...runs.map(r => [
          caseCode(r.id),
          r.invoice.vendor || "",
          r.invoice.invoice_number || "",
          r.result.matched_po?.po_number || r.invoice.po_number || "",
          r.invoice.total ?? "",
          r.invoice.currency || "USD",
          r.result.risk_engine?.score ?? "",
          r.result.risk_engine?.level ?? "",
          r.result.decision,
          r.status,
          r.priority || "MEDIUM",
          r.assigned_to || "",
          r.created_at
        ])
      ];
      const csv = rows.map(r => r.map(v => `"${String(v).replaceAll('"', '""')}"`).join(",")).join("\r\n");
      downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8;" }), "mosaic-ap-case-archive.csv");
      toast("Case history CSV archive downloaded.");
    } catch (err) { toast(err.message); }
  });

  loadWorkspace();
}

window.addEventListener("beforeunload", () => {
  if (state.currentPdfUrl?.startsWith("blob:")) URL.revokeObjectURL(state.currentPdfUrl);
});

init();
