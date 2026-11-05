# Mosaic AP Enterprise — Intelligent Accounts Payable Platform

**Mosaic AP Enterprise** is a production-grade, AI-powered accounts payable and invoice review platform. It combines automated document intelligence, evidence-backed three-way invoice matching, an explainable risk scoring engine, vendor master intelligence, smart exception resolution workflows, an embedded AI review assistant, and an immutable compliance audit trail.

Live Deployment: [https://mosaic-ap.onrender.com/](https://mosaic-ap.onrender.com/)

---

## Key Enterprise Capabilities

### 1. Evidence-Backed Three-Way Matching
- Reconciles **Supplier Invoices (Line Items)** ↔ **Purchase Orders (PO Lines)** ↔ **Goods Receipt Notes (GRN)**.
- Compares SKU, item description, ordered quantity, received quantity, invoiced quantity, and approved unit pricing.
- Identifies critical procurement exceptions:
  - Invoiced quantity exceeding goods receipt receiving (`QTY_EXCEEDS_GRN`).
  - Invoiced quantity exceeding authorized purchase order cap (`QTY_EXCEEDS_PO`).
  - Unit price discrepancies exceeding configured variance tolerances (`PRICE_MISMATCH`).
  - Missing goods receipt documentation (`MISSING_GRN`).
  - Partial shipment reconciliation (`PARTIAL_RECEIPT`).
  - Unordered line items on invoice (`UNORDERED_ITEM`).

### 2. Explainable Invoice Risk Engine (0 – 100)
- Calculates a deterministic, explainable risk score from 0 to 100.
- Categorizes risk into **Low (0-29)**, **Moderate (30-59)**, **High (60-84)**, and **Critical (85-100)**.
- Transparent mathematical factor breakdown:
  - Cryptographic duplicate invoice submission (+50 pts)
  - Historical reference collision across suppliers (+35 pts)
  - Supplier identity mismatch (+45 pts)
  - Unverified vendor profile or unverified remittance bank details (+25 to +30 pts)
  - Missing or unapproved purchase order (+25 to +30 pts)
  - Three-way quantity or price mismatch (+20 to +35 pts)
  - Subtotal and tax arithmetic tie failure (+25 pts)
  - Cumulative PO spending cap overage (+30 pts)
  - Scanned image / unreadable text layer (+20 pts)
  - Future or ambiguous invoice calendar date (+15 to +20 pts)
- Generates context-aware, step-by-step resolution actions for AP controllers.

### 3. Smart Exception Resolution & Human-in-the-Loop Governance
- Dedicated AP triage queue with priority routing (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- Multi-tier approval routing:
  - **Tier 1:** Standard AP Specialist Clearance (< $2,500)
  - **Tier 2:** AP Manager Review Required ($2,500 – $10,000)
  - **Tier 3:** Financial Controller / CFO Dual Authorization (> $10,000 or Critical Risk)
- Case workflow state management (`NEW`, `IN_REVIEW`, `WAITING`, `ESCALATED`, `RESOLVED`).
- Reviewer disposition override with mandatory justification rationale.
- Field-level extraction corrections retained as continuous model evaluation feedback.
- Immutable, chronological audit timeline tracking every system and reviewer action.

### 4. Vendor Intelligence & Remittance Verification
- Dedicated Supplier Master Directory with risk profiling.
- Automated remittance bank account verification against master data to detect diverted account details and prevent Business Email Compromise (BEC) fraud.
- Vendor performance analytics: lifetime spend, invoice volume, average invoice value, and historical exception rates.

### 5. Embedded AI Review Assistant
- Interactive AI review assistant embedded directly in the Review Workbench.
- Grounded strictly in verified case facts: PO commitments, receiving lines, tax calculations, and vendor status.
- Zero hallucinations: clearly cites structured document evidence and line items.
- Answers key inquiries:
  - *"Why was this invoice flagged?"*
  - *"Which fields do not match the PO or GRN?"*
  - *"What should the reviewer do next?"*
  - *"Summarize this invoice"*
  - Free-form natural language questions regarding pricing, dates, and receiving.

### 6. Document Intelligence & OCR Architecture
- Structured line item extraction (SKU, description, quantity, rate, total).
- Field-level extraction confidence scoring (0.0 to 1.0).
- Automatic detection of digital selectable text versus image-only scanned PDFs.

---

## Product Modules & Views

- **Review Desk:** Interactive invoice intake, drag-and-drop upload (up to 15 MB), prepared enterprise test scenarios, real-time control execution, and side-by-side preview.
- **Exception Queue:** Priority-based AP triage workspace, multi-criteria filtering, risk badges, quick assignment, and quick triage actions.
- **Review Workbench:** Deep inspection console with 3-way matching table, explainable risk meter, AI assistant, reviewer override form, extraction corrections, and audit history.
- **Vendor Intelligence:** Centralized vendor master directory, bank account verification status, and supplier risk metrics.
- **Case History:** Searchable archive of all historical reviews with filtering, downloadable JSON case packets, and CSV export.
- **Analytics Dashboard:** Real-time financial metrics, invoiced value, pending review value, discrepancies intercepted ($), 7-day trend charts, and vendor spend breakdown.
- **How It Works:** Interactive 7-stage AP pipeline visualizer, governance boundary matrix, and live edge-case rehearsal runner.

---

## Project Structure

```
asa-invoice-review/
├── app.py                         # Application entrypoint
├── webapp.py                      # HTTP server, routing & REST APIs
├── asa_engine.py                  # Core engine: 3-way match, risk engine, extractor, AI assistant
├── make_fixtures.py               # Generates synthetic invoice test scenarios
├── requirements.txt               # Dependencies (pypdf, reportlab)
├── frontend/
│   ├── index.html                 # Redesigned enterprise application UI
│   ├── app.js                     # State management, view rendering & API interactions
│   └── styles.css                 # Fintech design system & responsive styling
├── data/
│   ├── invoices/                  # Synthetic test PDF invoice scenarios
│   ├── purchase_orders/
│   │   ├── purchase_orders.csv    # Purchase order commitments register
│   │   └── purchase_order_lines.json # Itemized lines for PO commitments
│   ├── goods_receipts/
│   │   └── goods_receipts.json    # Goods Receipt Notes (GRN) warehouse receiving data
│   └── vendors/
│       └── vendors.json           # Vendor master records & verified bank accounts
├── runs/
│   └── history.sqlite3            # SQLite database storing runs, cases, and audit trails
└── tests/
    ├── test_engine.py             # Core engine unit tests
    ├── test_api_helpers.py        # Web handler & endpoint tests
    ├── test_sample_pdf_route.py   # PDF serving tests
    └── test_enterprise_features.py # 3-way matching, risk scoring, vendor & AI assistant tests
```

---

## Quick Start & Local Run

### Prerequisites
- Python 3.10 or newer

### Setup Instructions

1. **Clone the repository and navigate to the directory:**
   ```sh
   git clone <repo-url>
   cd asa-invoice-review
   ```

2. **Create and activate a virtual environment:**
   - **Windows:**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\activate
     ```
   - **macOS / Linux:**
     ```sh
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

4. **(Optional) Re-generate test scenario fixtures:**
   ```sh
   python make_fixtures.py
   ```

5. **Start the application:**
   - **Windows (PowerShell):**
     ```powershell
     $env:HOST = "127.0.0.1"
     $env:PORT = "8501"
     $env:RESET_DB_ON_START = "false"
     python app.py
     ```
   - **macOS / Linux:**
     ```sh
     export HOST=127.0.0.1
     export PORT=8501
     export RESET_DB_ON_START=false
     python app.py
     ```

6. **Open in browser:**
   Open `http://localhost:8501` in your browser.

---

## Testing

Run the automated test suite (30 unit and integration tests):

```sh
python -m unittest discover tests
```

All tests execute in-process and verify:
- Three-way quantity mismatch detection against Goods Receipt Notes (GRN).
- Clean 3-way matching clearance.
- Explainable risk engine scoring and factor contributions.
- Vendor master data lookup and banking verification.
- Context-aware AI assistant responses and evidence citations.
- Case priority escalation and reviewer resolution tracking.
- Financial analytics calculations.
- Web API endpoint handling and PDF streaming.

---

## Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `HOST` | `127.0.0.1` | Network interface to bind (`0.0.0.0` for cloud deployment). |
| `PORT` | `8501` | Listening port (assigned by Render/Heroku/AWS). |
| `RESET_DB_ON_START` | `false` | When `true`, resets SQLite database on every server startup. |
| `DB_PATH` | `runs/history.sqlite3` | File path for SQLite persistence. Set to `/tmp/...` for ephemeral storage. |
| `OPENAI_API_KEY` | *(Optional)* | Optional external model provider key for augmented conversational queries. |
| `GEMINI_API_KEY` | *(Optional)* | Optional Gemini API key for external LLM augmentation. |

---

## Cloud Deployment (Render / Container Hosts)

The application is fully compatible with Render, Railway, AWS ECS, and Docker.

1. **Build Command:**
   ```sh
   pip install -r requirements.txt && python make_fixtures.py
   ```
2. **Start Command:**
   ```sh
   python app.py
   ```
3. **Environment Settings on Render:**
   - `HOST`: `0.0.0.0`
   - `PORT`: `10000` (or Render's automatic port)
   - `RESET_DB_ON_START`: `false` (or `true` if stateless demo instance preferred)

---

## Core Enterprise Test Scenarios Included

Mosaic AP includes dedicated synthetic scenarios to demonstrate edge cases:

1. **Clean 3-Way Match (`happy_path.pdf`):** Invoiced line items match PO-1001 and GRN-9001 receiving exactly. Clear clearance. Risk: Low (4/100).
2. **3-Way Quantity Mismatch (`quantity_mismatch.pdf`):** Invoiced 5 motors against PO-1006, but GRN-9005 records only 3 units received. Risk: High (78/100). Flags `GRN_QUANTITY_MISMATCH`.
3. **Duplicate Submission (`duplicate_invoice.pdf`):** Cryptographic SHA-256 fingerprint matches earlier submission. Immediate stop. Risk: Critical (95/100).
4. **Tax & Math Mismatch (`cents_mismatch.pdf`):** Subtotal ($1,150.00) + Tax ($100.00) != Total ($1,215.00). Flags `TOTAL_MATH_MISMATCH`.
5. **Unapproved PO (`pending_po.pdf`):** Linked PO is in `pending` procurement status. Flags `PO_NOT_APPROVED`.
6. **Supplier Variant (`supplier_name_variant.pdf`):** Similar but non-identical trading name. Flags `VENDOR_NAME_VARIANT`.
7. **Supplier Mismatch (`vendor_mismatch.pdf`):** Impostor or incorrect supplier billing against another vendor's PO. Flags `VENDOR_MISMATCH`. Risk: Critical (98/100).
8. **Scanned Document Scan (`image_only_scan.pdf`):** Detects zero selectable digital text and routes to OCR pipeline.

---

## Compliance & Governance Principles

- **Deterministic Financial Controls:** Numerical math, 3-way matching, and tolerance thresholds are computed deterministically. AI does not hallucinate or guess payable balances.
- **Audit Traceability:** Reviewer overrides require explicit rationale and are permanently logged with timestamps.
- **Private & Local First:** Invoices and data stay strictly within the deployment environment. No third-party API exposure is required.
