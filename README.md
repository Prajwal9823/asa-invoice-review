# Mosaic AP | Invoice Review

Mosaic AP is an accounts payable review prototype for comparing invoice evidence with purchase orders. It combines document extraction, explainable controls, exception handling, reviewer feedback, and an audit trail in one case workflow.

## Quick start

Requires Python 3.10 or newer. From the repository root:

Create the environment:

```sh
python -m venv .venv
```

On Windows, install and start with:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:HOST = "127.0.0.1"
$env:PORT = "8501"
$env:RESET_DB_ON_START = "false"
.venv\Scripts\python.exe app.py
```

On macOS or Linux, use:

```sh
.venv/bin/python -m pip install -r requirements.txt
export HOST=127.0.0.1
export PORT=8501
export RESET_DB_ON_START=false
.venv/bin/python app.py
```

For a public deployment, set `HOST=0.0.0.0` and `RESET_DB_ON_START=true`. The app reads its SQLite database path from `DB_PATH`, and the default is `runs/history.sqlite3`. If you want a fresh public instance, either point `DB_PATH` at a temporary file or delete the history file on startup.

Open `http://localhost:8501` in a browser for local use. For a cloud deployment, expose the app through your host's HTTPS endpoint instead of loopback.

## Public deployment setup

1. Create a cloud service account or deploy to a container host.
2. Set `HOST=0.0.0.0` and `PORT=<your-platform-port>`.
3. Set `RESET_DB_ON_START=true` if you want every fresh instance to start empty.
4. Optionally set `DB_PATH=/tmp/mosaic-history.sqlite3` so the database is ephemeral.
5. Launch the app and connect it to your public HTTPS URL.

This project is still a prototype; it does not include authentication, multi-user isolation, or production retention controls.

## Review workflow

1. Select a prepared scenario or upload a PDF invoice.
2. Inspect extracted fields beside the source document and matched purchase order.
3. Open evidence under each control to see the source text or register value behind it.
4. Review the PO commitment timeline, including previously approved invoices and the projected remaining balance.
5. Move the case through the exception queue, assign an owner, add notes, and record a reviewer disposition when it differs from the model recommendation.
6. Correct extraction fields with a reason. Corrections are retained as evaluation feedback; they do not silently change the original model result.
7. Download the case audit JSON with evidence, notes, corrections, status changes, and reviewer activity.

## Product areas

- **Review Desk:** original invoice, extracted fields, purchase order, evidence-linked checks, and recommendation.
- **Review Queue:** open exceptions, work state, assignment, corrections, reviewer disposition, PO balance, and activity timeline.
- **Case History:** searchable cases and CSV export.
- **Analytics:** review outcomes, recent workload, reviewer corrections, and disposition overrides.
- **How it Works:** policy rules and model boundaries.

Queue shortcuts: `J` / `K` move between cases, `N` focuses the note field, and `E` focuses work state. `Ctrl+K` opens the command palette.

## Decision boundaries

Mosaic extracts selectable PDF text. Image-only scans are flagged for human review; OCR is not included. Supplier similarity is advisory and never silently selects a purchase order. The system recommends an outcome but never initiates a payment. Reviewer overrides remain separate from the model recommendation, with a required rationale.

The included purchase orders and invoice scenarios are synthetic. The rules and interface are a case-study prototype, not a production payable control system.

## Project structure

- `app.py` starts the application.
- `webapp.py` provides the HTTP interface and case APIs.
- `asa_engine.py` extracts invoice fields, evaluates controls, and manages case history.
- `frontend/` contains the responsive interface.
- `data/purchase_orders/` contains the synthetic purchase order register.
- `data/invoices/` contains the synthetic invoice scenarios.
- `tests/` contains unit and API-helper checks.
