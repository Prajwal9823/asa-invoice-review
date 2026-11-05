from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

ROOT = Path(__file__).parent
DEFAULT_DB_PATH = ROOT / "runs" / "history.sqlite3"
raw_db_path = os.getenv("DB_PATH")
if raw_db_path:
    candidate = Path(raw_db_path).expanduser()
    DB_PATH = candidate if candidate.is_absolute() else (ROOT / candidate).resolve()
else:
    DB_PATH = DEFAULT_DB_PATH
PO_PATH = ROOT / "data" / "purchase_orders" / "purchase_orders.csv"
CURRENCIES = {"USD", "EUR", "GBP", "INR", "CAD", "AUD"}


@dataclass(frozen=True)
class Invoice:
    invoice_number: str | None
    invoice_date: str | None
    vendor: str | None
    po_number: str | None
    total: float | None
    currency: str | None
    subtotal: float | None
    tax: float | None
    source: str
    sha256: str
    raw_text: str
    date_ambiguous: bool = False


def extract_text(pdf_bytes: bytes) -> str:
    """Extract selectable text. Image-only PDFs remain explicit manual-review cases."""
    reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    return "\n\f\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _first(patterns: list[str], text: str, flags: int = re.I) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip(" #:\t")
    return None


def _money(patterns: list[str], text: str) -> float | None:
    raw = _first(patterns, text)
    if not raw:
        return None
    value = raw.strip()
    negative = value.startswith("-") or (value.startswith("(") and value.endswith(")"))
    value = re.sub(r"[()\s$€£₹]", "", value)
    try:
        number = float(value.replace(",", ""))
        return -abs(number) if negative else number
    except ValueError:
        return None


def _parse_date(raw: str | None) -> tuple[str | None, bool]:
    if not raw:
        return None, False
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat(), False
        except ValueError:
            return raw, False
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", raw)
    if not match:
        return raw, False
    first, second, year = map(int, match.groups())
    year = year + (2000 if year < 70 else 1900) if year < 100 else year
    if first <= 12 and second <= 12 and first != second:
        return raw, True
    day, month = (first, second) if first > 12 else (second, first)
    try:
        return date(year, month, day).isoformat(), False
    except ValueError:
        return raw, False


def parse_invoice(text: str, source: str, digest: str) -> Invoice:
    vendor = _first([
        r"(?:vendor|supplier|bill\s*from)\s*[:#-]\s*([^\n]+)",
        r"^\s*([A-Z][A-Za-z0-9 &.,'-]{2,55})\s+(?:INVOICE|BILL)\s*$",
    ], text, re.I | re.M)
    invoice_number = _first([
        r"(?:invoice\s*(?:number|no\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9./_-]*)"
    ], text)
    raw_date = _first([
        r"(?:invoice\s*)?date\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    ], text)
    invoice_date, date_ambiguous = _parse_date(raw_date)
    po_number = _first([
        r"(?:purchase\s*order|PO)\s*(?:number|no\.?|#)?\s*[:#-]?\s*((?:PO[- ])?[A-Z0-9][A-Z0-9_-]*)"
    ], text)
    currency_match = re.search(r"\b(USD|EUR|GBP|INR|CAD|AUD)\b|([$€£₹])\s*[-(]?\s*\d", text, re.I)
    currency = None
    if currency_match:
        currency = currency_match.group(1).upper() if currency_match.group(1) else {
            "$":"USD", "€":"EUR", "£":"GBP", "₹":"INR"
        }.get(currency_match.group(2))
    amount = r"(?:USD|EUR|GBP|INR|CAD|AUD)?\s*(\(?-?\s*[$€£₹]?\s*[\d,]+(?:\.\d{1,2})?\)?)"
    total = _money([rf"(?:grand\s*total|invoice\s*total|amount\s*due|total\s*due|\btotal\b)\s*[:\-]?\s*{amount}"], text)
    subtotal = _money([rf"(?:sub\s*total|subtotal)\s*[:\-]?\s*{amount}"], text)
    tax = _money([rf"(?:sales\s*tax|tax|VAT|GST)\s*[:\-]?\s*{amount}"], text)
    return Invoice(invoice_number, invoice_date, vendor, po_number, total, currency, subtotal, tax,
                   source, digest, text, date_ambiguous)


def load_pos(path: Path = PO_PATH) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"po_number", "vendor", "approved_amount", "currency", "status"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"PO register must contain: {', '.join(sorted(required))}")
        rows = list(reader)
    seen: set[str] = set()
    for row in rows:
        po_number = (row.get("po_number") or "").strip()
        if not po_number or po_number.casefold() in seen:
            raise ValueError("PO register contains a missing or duplicate PO number")
        seen.add(po_number.casefold())
        row["po_number"] = po_number
        row["vendor"] = (row.get("vendor") or "").strip()
        row["approved_amount"] = float(row["approved_amount"])
        if row["approved_amount"] <= 0:
            raise ValueError(f"PO {po_number} must have a positive approved amount")
        row["currency"] = (row.get("currency") or "").strip().upper()
        if row["currency"] not in CURRENCIES:
            raise ValueError(f"PO {po_number} has an unsupported currency")
        row["status"] = (row.get("status") or "").strip().lower()
    return rows


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    folded = re.sub(r"\b(incorporated|inc|limited|ltd|llc|corp|corporation|company|co)\b", " ", folded)
    return re.sub(r"[^a-z0-9]+", "", folded)


def _candidate_pos(invoice: Invoice, pos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank PO leads using a transparent, renormalized weighted feature score."""
    candidates: list[dict[str, Any]] = []
    for po in pos:
        features: dict[str, float] = {
            "supplier_similarity": difflib.SequenceMatcher(None, _normalize(invoice.vendor), _normalize(po["vendor"])).ratio()
        }
        weights = {"supplier_similarity":0.58}
        if invoice.total is not None:
            features["amount_similarity"] = max(0.0, 1 - abs(invoice.total - po["approved_amount"]) / po["approved_amount"])
            weights["amount_similarity"] = 0.22
        if invoice.po_number:
            features["reference_similarity"] = difflib.SequenceMatcher(None, _normalize(invoice.po_number), _normalize(po["po_number"])).ratio()
            weights["reference_similarity"] = 0.10
        if invoice.currency:
            features["currency_match"] = float(invoice.currency == po["currency"])
            weights["currency_match"] = 0.10
        score = sum(features[key] * weights[key] for key in features) / sum(weights[key] for key in features)
        candidates.append({"po_number":po["po_number"], "vendor":po["vendor"], "approved_amount":po["approved_amount"],
                           "currency":po["currency"], "status":po["status"], "score":round(score, 3),
                           "signals":{key:round(value, 3) for key, value in features.items()}})
    return sorted(candidates, key=lambda item:(-item["score"], item["po_number"]))[:3]


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, filename TEXT NOT NULL,
            sha256 TEXT NOT NULL, invoice_json TEXT NOT NULL, result_json TEXT NOT NULL)""")
        conn.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("""CREATE TABLE IF NOT EXISTS case_meta (
            run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'NEW', assigned_to TEXT NOT NULL DEFAULT '',
            corrections_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL,
            decision_override TEXT NOT NULL DEFAULT '', override_rationale TEXT NOT NULL DEFAULT '')""")
        conn.execute("""CREATE TABLE IF NOT EXISTS case_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, message TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL)""")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        for name, declaration in {"invoice_number_norm":"TEXT", "vendor_norm":"TEXT", "po_number":"TEXT", "total":"REAL", "decision":"TEXT"}.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {declaration}")
        migrated = conn.execute("SELECT value FROM app_meta WHERE key='run-indexes-v1'").fetchone()
        if not migrated:
            for run_id, invoice_raw, result_raw in conn.execute("SELECT id,invoice_json,result_json FROM runs").fetchall():
                invoice, result = json.loads(invoice_raw), json.loads(result_raw)
                po = result.get("matched_po") or {}
                conn.execute("UPDATE runs SET invoice_number_norm=?,vendor_norm=?,po_number=?,total=?,decision=? WHERE id=?",
                    (_normalize(invoice.get("invoice_number")), _normalize(invoice.get("vendor")),
                     po.get("po_number") or invoice.get("po_number"), invoice.get("total"), result.get("decision"), run_id))
            conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('run-indexes-v1','done')")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_sha256 ON runs(sha256)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_reference ON runs(invoice_number_norm,vendor_norm)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_po_decision ON runs(po_number,decision)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_case_events_run ON case_events(run_id,id)")
        case_columns = {row[1] for row in conn.execute("PRAGMA table_info(case_meta)")}
        if "decision_override" not in case_columns:
            conn.execute("ALTER TABLE case_meta ADD COLUMN decision_override TEXT NOT NULL DEFAULT ''")
        if "override_rationale" not in case_columns:
            conn.execute("ALTER TABLE case_meta ADD COLUMN override_rationale TEXT NOT NULL DEFAULT ''")
        conn.execute("INSERT OR IGNORE INTO case_meta(run_id,status,assigned_to,corrections_json,updated_at) SELECT id,'NEW','','{}',created_at FROM runs")
        conn.execute("""INSERT INTO case_events(run_id,kind,message,payload_json,created_at)
            SELECT r.id,'created','Case imported from existing review history.','{}',r.created_at FROM runs r
            WHERE NOT EXISTS (SELECT 1 FROM case_events e WHERE e.run_id=r.id)""")


def _case_row(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("""SELECT r.id,r.created_at,r.filename,r.sha256,r.invoice_json,r.result_json,
            m.status,m.assigned_to,m.corrections_json,m.updated_at,m.decision_override,m.override_rationale
            FROM runs r LEFT JOIN case_meta m ON m.run_id=r.id WHERE r.id=?""", (run_id,)).fetchone()
        if not row:
            return None
        events = conn.execute("SELECT id,kind,message,payload_json,created_at FROM case_events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        related = conn.execute("""SELECT id,invoice_json FROM runs WHERE id<>? AND
            ((invoice_number_norm=? AND vendor_norm=?) OR sha256=?) ORDER BY id DESC LIMIT 1""",
            (run_id, _normalize(json.loads(row[4]).get("invoice_number")), _normalize(json.loads(row[4]).get("vendor")), row[3])).fetchone()
    invoice = json.loads(row[4])
    result = json.loads(row[5])
    if result.get("po_balance") is None and result.get("matched_po") and invoice.get("total") is not None:
        po = result["matched_po"]
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            prior = conn.execute("SELECT COALESCE(SUM(total),0) FROM runs WHERE po_number=? AND decision='APPROVE' AND id<?",
                                 (po.get("po_number"),run_id)).fetchone()[0]
        result["po_balance"] = {"currency":po.get("currency"),"commitment":po.get("approved_amount"),
                                "previously_approved":float(prior or 0),"this_invoice":invoice["total"],
                                "remaining_after":round(float(po.get("approved_amount") or 0)-float(prior or 0)-float(invoice["total"]),2)}
    comparison = None
    if related:
        previous = json.loads(related[1])
        fields = ("invoice_number", "invoice_date", "vendor", "po_number", "total", "currency", "subtotal", "tax")
        changes = [{"field":key,"before":previous.get(key),"after":json.loads(row[4]).get(key)}
                   for key in fields if previous.get(key) != json.loads(row[4]).get(key)]
        comparison = {"case_id":related[0],"changes":changes}
    return {"id":row[0],"created_at":row[1],"filename":row[2],"invoice":invoice,"result":result,
            "status":row[6] or "NEW","assigned_to":row[7] or "","corrections":json.loads(row[8] or "{}"),
            "updated_at":row[9] or row[1],"events":[{"id":e[0],"kind":e[1],"message":e[2],"payload":json.loads(e[3]),"created_at":e[4]} for e in events],
            "decision_override":row[10] or "","override_rationale":row[11] or "",
            "comparison":comparison}


def get_case(run_id: int) -> dict[str, Any] | None:
    return _case_row(run_id)


def update_case(run_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
    init_db()
    allowed_changes = {"status", "assigned_to", "correction", "note", "decision_override", "override_rationale"}
    unknown_changes = set(changes) - allowed_changes
    if unknown_changes:
        raise ValueError("Unsupported case update field.")
    valid_statuses = {"NEW", "IN_REVIEW", "WAITING", "RESOLVED"}
    allowed_fields = {"invoice_number", "invoice_date", "vendor", "po_number", "total", "currency", "subtotal", "tax"}
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=10000")
        run = conn.execute("SELECT invoice_json FROM runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            return None
        original_invoice = json.loads(run[0])
        meta = conn.execute("SELECT status,assigned_to,corrections_json,decision_override,override_rationale FROM case_meta WHERE run_id=?", (run_id,)).fetchone()
        status, assigned_to, corrections_raw, decision_override, override_rationale = meta or ("NEW", "", "{}", "", "")
        corrections = json.loads(corrections_raw or "{}")
        now = datetime.now(timezone.utc).isoformat()

        def event(kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
            conn.execute("INSERT INTO case_events(run_id,kind,message,payload_json,created_at) VALUES(?,?,?,?,?)",
                         (run_id,kind,message,json.dumps(payload or {},ensure_ascii=False),now))

        if "status" in changes:
            next_status = str(changes["status"]).upper()
            if next_status not in valid_statuses:
                raise ValueError("Choose a valid case status.")
            if next_status != status:
                event("status",f"Status changed from {status.replace('_',' ').title()} to {next_status.replace('_',' ').title()}.",{"from":status,"to":next_status})
                status = next_status
        if "assigned_to" in changes:
            next_assignee = str(changes["assigned_to"] or "").strip()[:80]
            if next_assignee != assigned_to:
                event("assignment",f"Assigned to {next_assignee or 'unassigned'}.",{"from":assigned_to,"to":next_assignee})
                assigned_to = next_assignee
        if "decision_override" in changes:
            next_override = str(changes["decision_override"] or "").upper()
            if next_override not in {"", "APPROVE", "REVIEW", "REJECT"}:
                raise ValueError("Choose a valid reviewer disposition.")
            next_rationale = str(changes.get("override_rationale", override_rationale) or "").strip()[:500]
            if next_override and not next_rationale:
                raise ValueError("Explain why the model recommendation is being overridden.")
            if next_override != decision_override or next_rationale != override_rationale:
                event("disposition",f"Reviewer disposition set to {next_override or 'model recommendation'}.",
                      {"from":decision_override,"to":next_override,"rationale":next_rationale})
                decision_override, override_rationale = next_override, next_rationale
        elif "override_rationale" in changes:
            override_rationale = str(changes["override_rationale"] or "").strip()[:500]
        if "note" in changes:
            note = str(changes["note"] or "").strip()
            if note:
                if len(note) > 2000:
                    raise ValueError("Notes must be 2,000 characters or fewer.")
                event("note",note)
        correction = changes.get("correction")
        if correction:
            if not isinstance(correction, dict):
                raise ValueError("Correction must include a field, value, and reason.")
            field = str(correction.get("field", ""))
            rationale = str(correction.get("rationale", "")).strip()[:500]
            if field not in allowed_fields or not rationale:
                raise ValueError("Choose a supported field and explain the correction.")
            raw_value = correction.get("value")
            if field in {"total", "subtotal", "tax"}:
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    raise ValueError("Enter a valid numeric amount.") from None
                if not math.isfinite(value) or abs(value) > 1_000_000_000:
                    raise ValueError("Enter a finite amount within the supported range.")
            else:
                value = str(raw_value or "").strip()[:160]
                if not value:
                    raise ValueError("Corrected value cannot be blank.")
            original = original_invoice.get(field)
            corrections[field] = {"original":original,"corrected":value,"rationale":rationale,"updated_at":now}
            event("correction",f"{field.replace('_',' ').title()} corrected by reviewer.",{"field":field,"original":original,"corrected":value,"rationale":rationale})
        conn.execute("INSERT INTO case_meta(run_id,status,assigned_to,corrections_json,updated_at,decision_override,override_rationale) VALUES(?,?,?,?,?,?,?) "
                     "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,assigned_to=excluded.assigned_to,corrections_json=excluded.corrections_json,updated_at=excluded.updated_at,decision_override=excluded.decision_override,override_rationale=excluded.override_rationale",
                     (run_id,status,assigned_to,json.dumps(corrections,ensure_ascii=False),now,decision_override,override_rationale))
    return _case_row(run_id)


def find_duplicate(invoice_number: str | None, vendor: str | None, digest: str) -> int | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT id FROM runs WHERE sha256=? ORDER BY id DESC LIMIT 1", (digest,)).fetchone()
        if row:
            return int(row[0])
        invoice_key, vendor_key = _normalize(invoice_number), _normalize(vendor)
        if not invoice_key or not vendor_key:
            return None
        row = conn.execute("SELECT id FROM runs WHERE invoice_number_norm=? AND vendor_norm=? ORDER BY id DESC LIMIT 1", (invoice_key, vendor_key)).fetchone()
        return int(row[0]) if row else None


def find_reference_collision(invoice_number: str | None, vendor: str | None) -> int | None:
    if not invoice_number or not _normalize(vendor):
        return None
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT id FROM runs WHERE invoice_number_norm=? AND vendor_norm<>? ORDER BY id DESC LIMIT 1",
                           (_normalize(invoice_number), _normalize(vendor))).fetchone()
        return int(row[0]) if row else None


def _previous_approved_billing(po_number: str) -> float:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT COALESCE(SUM(total),0) FROM runs WHERE po_number=? AND decision='APPROVE'", (po_number,)).fetchone()
    return float(row[0] or 0)


def _checks(invoice: Invoice, po: dict[str, Any] | None = None, flags: list[str] | None = None,
            tolerance_pct: float = 2.0) -> list[dict[str, str]]:
    flags = flags or []
    if invoice.date_ambiguous:
        date_status, date_detail = "review", f"{invoice.invoice_date} · locale ambiguous"
    elif invoice.invoice_date:
        try:
            invoice_day = date.fromisoformat(invoice.invoice_date)
            date_status = "review" if invoice_day > date.today() else "pass"
            date_detail = f"{invoice.invoice_date} · future date" if invoice_day > date.today() else invoice.invoice_date
        except ValueError:
            date_status, date_detail = "fail", f"{invoice.invoice_date} · invalid calendar date"
    else:
        date_status, date_detail = "review", "Could not identify a date"
    dup_status = "fail" if "DUPLICATE" in flags else "review" if "REFERENCE_COLLISION" in flags else "pass"
    dup_detail = "Previously reviewed invoice found" if dup_status == "fail" else "Reference appears under another supplier" if dup_status == "review" else "No earlier matching submission"
    checks = [
        {"name":"Invoice number", "status":"pass" if invoice.invoice_number else "review", "detail":invoice.invoice_number or "Could not identify a reference"},
        {"name":"Invoice date", "status":date_status, "detail":date_detail},
        {"name":"Supplier identity", "status":"pass" if invoice.vendor else "review", "detail":invoice.vendor or "Could not identify a supplier"},
        {"name":"PO reference", "status":"pass" if invoice.po_number else "review", "detail":invoice.po_number or "No PO number found"},
        {"name":"Invoice total", "status":"pass" if invoice.total is not None and invoice.total > 0 else "review", "detail":f"{invoice.currency or ''} {invoice.total:,.2f}" if invoice.total is not None else "No payable total found"},
        {"name":"Duplicate screen", "status":dup_status, "detail":dup_detail},
    ]
    if invoice.subtotal is not None or invoice.tax is not None:
        if invoice.subtotal is not None and invoice.tax is not None and invoice.total is not None:
            delta = abs(invoice.subtotal + invoice.tax - invoice.total)
            checks.append({"name":"Subtotal + tax", "status":"pass" if delta <= 0.02 else "fail", "detail":f"{invoice.subtotal:,.2f} + {invoice.tax:,.2f} vs {invoice.total:,.2f}"})
        else:
            checks.append({"name":"Subtotal + tax", "status":"review", "detail":"Only part of the invoice arithmetic was available"})
    if po:
        similarity = difflib.SequenceMatcher(None, _normalize(invoice.vendor), _normalize(po["vendor"])).ratio()
        supplier_status = "pass" if similarity >= 0.98 else "review" if similarity >= 0.72 else "fail"
        checks.extend([
            {"name":"Supplier ↔ PO", "status":supplier_status, "detail":f"Invoice: {invoice.vendor} · PO: {po['vendor']} · {similarity:.0%} name similarity"},
            {"name":"PO status", "status":"pass" if po["status"] == "approved" else "review", "detail":po["status"].title()},
            {"name":"Currency", "status":"pass" if invoice.currency == po["currency"] else "review" if not invoice.currency else "fail", "detail":f"Invoice: {invoice.currency or 'unknown'} · PO: {po['currency']}"},
        ])
        if invoice.total is not None:
            prior = _previous_approved_billing(po["po_number"])
            billed = prior + invoice.total
            cap = po["approved_amount"] * (1 + tolerance_pct / 100)
            if billed > cap:
                balance_status = "review"
                balance_detail = f"{po['currency']} {billed:,.2f} incl. {po['currency']} {prior:,.2f} previously approved · PO {po['currency']} {po['approved_amount']:,.2f}"
            elif invoice.total < po["approved_amount"] - 0.02:
                balance_status = "review"
                balance_detail = f"Possible partial billing · {po['currency']} {max(0, po['approved_amount']-billed):,.2f} remains after this invoice"
            elif billed > po["approved_amount"]:
                balance_status = "pass"
                balance_detail = f"{po['currency']} {billed:,.2f} including this invoice · within {tolerance_pct:.1f}% allowance"
            else:
                balance_status = "pass"
                balance_detail = f"{po['currency']} {billed:,.2f} of {po['currency']} {po['approved_amount']:,.2f} committed"
            checks.append({"name":"PO balance", "status":balance_status, "detail":balance_detail})
    if "OCR_REQUIRED" in flags:
        checks.append({"name":"Document readability", "status":"review", "detail":"No selectable text; manual review needed"})
    return checks


def _result(decision: str, reason: str, flags: list[str], invoice: Invoice, po: dict[str, Any] | None = None,
            variance: float | None = None, next_step: str = "", candidates: list[dict[str, Any]] | None = None,
            tolerance_pct: float = 2.0) -> dict[str, Any]:
    fields = [invoice.invoice_number, invoice.invoice_date if not invoice.date_ambiguous else None,
              invoice.vendor, invoice.po_number, invoice.total, invoice.currency]
    coverage = round(100 * sum(value is not None for value in fields) / len(fields))
    po_balance = None
    if po and invoice.total is not None:
        previously_approved = _previous_approved_billing(po["po_number"])
        po_balance = {"currency":po["currency"],"commitment":po["approved_amount"],
                      "previously_approved":previously_approved,"this_invoice":invoice.total,
                      "remaining_after":round(po["approved_amount"]-previously_approved-invoice.total,2)}
    return {"decision":decision, "reason":reason, "flags":flags, "matched_po":po, "variance":variance,
            "next_step":next_step, "evidence_coverage":coverage, "checks":_checks(invoice, po, flags, tolerance_pct),
            "candidates":candidates or [],"po_balance":po_balance}


def decide(invoice: Invoice, pos: list[dict[str, Any]], tolerance_pct: float = 2.0) -> dict[str, Any]:
    if not 0 <= tolerance_pct <= 10:
        raise ValueError("Tolerance must be between 0% and 10%")
    if not invoice.raw_text.strip():
        return _result("REVIEW", "I couldn't find selectable text in this PDF. It may be a scan, so no fields were guessed.", ["OCR_REQUIRED"], invoice, next_step="Ask AP to review the original or provide a text-readable copy.", tolerance_pct=tolerance_pct)
    duplicate = find_duplicate(invoice.invoice_number, invoice.vendor, invoice.sha256)
    if duplicate:
        return _result("REJECT", f"This looks like an invoice already reviewed in run #{duplicate} (same file or invoice reference and supplier).", ["DUPLICATE"], invoice, next_step="Check the earlier run before recording or paying this invoice.", tolerance_pct=tolerance_pct)
    collision = find_reference_collision(invoice.invoice_number, invoice.vendor)
    if collision:
        return _result("REVIEW", f"Invoice reference {invoice.invoice_number} already appears under a different supplier in run #{collision}.", ["REFERENCE_COLLISION"], invoice, next_step="Confirm the supplier and invoice number directly with the source document.", tolerance_pct=tolerance_pct)
    if invoice.date_ambiguous:
        return _result("REVIEW", f"The date {invoice.invoice_date} can be read in more than one way. Mosaic did not choose a locale.", ["AMBIGUOUS_INVOICE_DATE"], invoice, next_step="Confirm the date format from the supplier's source document.", tolerance_pct=tolerance_pct)
    missing = [name for name, value in [("invoice number", invoice.invoice_number), ("date", invoice.invoice_date), ("vendor", invoice.vendor), ("total", invoice.total)] if value is None]
    if missing:
        return _result("REVIEW", "I couldn't safely identify " + ", ".join(missing) + ". Nothing will be auto-approved while a required field is missing.", ["MISSING_REQUIRED_FIELDS"], invoice, next_step="Confirm the missing values against the source invoice.", tolerance_pct=tolerance_pct)
    if invoice.total is not None and invoice.total <= 0:
        return _result("REVIEW", "The total is zero or negative. This could be a credit note or an extraction issue, and needs a separate review path.", ["NON_POSITIVE_TOTAL"], invoice, next_step="Confirm whether this is a credit memo and route it through the credit-note process.", tolerance_pct=tolerance_pct)
    try:
        invoice_day = date.fromisoformat(invoice.invoice_date or "")
    except ValueError:
        return _result("REVIEW", f"The date '{invoice.invoice_date}' was not a valid calendar date.", ["INVALID_INVOICE_DATE"], invoice, next_step="Check the date on the original PDF.", tolerance_pct=tolerance_pct)
    if invoice_day > date.today():
        return _result("REVIEW", f"The invoice date ({invoice.invoice_date}) is in the future.", ["FUTURE_INVOICE_DATE"], invoice, next_step="Confirm the invoice date with the supplier.", tolerance_pct=tolerance_pct)
    if invoice.subtotal is not None and invoice.tax is not None and abs(invoice.subtotal + invoice.tax - invoice.total) > 0.02:
        delta = invoice.subtotal + invoice.tax - invoice.total
        return _result("REVIEW", f"The math doesn't tie: subtotal plus tax differs from the invoice total by {invoice.currency or ''} {abs(delta):,.2f}.", ["TOTAL_MATH_MISMATCH"], invoice, next_step="Ask AP to reconcile tax, discounts, credits, or omitted line items.", tolerance_pct=tolerance_pct)
    po = next((item for item in pos if invoice.po_number and item["po_number"].casefold() == invoice.po_number.casefold()), None)
    if not invoice.po_number or not po:
        candidates = _candidate_pos(invoice, pos)
        best = candidates[0] if candidates else None
        why = "No PO reference was found." if not invoice.po_number else f"PO {invoice.po_number} is not in the register."
        hint = f" Closest register lead: {best['po_number']} for {best['vendor']} ({best['score']:.0%} relative fit); this is only a suggestion." if best and best["score"] >= 0.45 else ""
        return _result("REVIEW", why + hint, ["PO_REFERENCE_MISSING" if not invoice.po_number else "PO_NOT_FOUND"], invoice,
                       next_step="Confirm the correct PO with the requester; candidate matches are advisory only.", candidates=candidates, tolerance_pct=tolerance_pct)
    vendor_score = difflib.SequenceMatcher(None, _normalize(invoice.vendor), _normalize(po["vendor"])).ratio()
    if vendor_score < 0.72:
        return _result("REJECT", f"Supplier mismatch: the invoice names {invoice.vendor}, while {po['po_number']} belongs to {po['vendor']}.", ["VENDOR_MISMATCH"], invoice, po,
                       next_step="Confirm the supplier identity and PO before any payment is considered.", tolerance_pct=tolerance_pct)
    if vendor_score < 0.98:
        return _result("REVIEW", f"Supplier names are similar but not identical ({vendor_score:.0%} match): '{invoice.vendor}' vs '{po['vendor']}'.", ["VENDOR_NAME_VARIANT"], invoice, po,
                       next_step="Confirm this is an approved trading-name variation; fuzzy matches are never auto-approved.", tolerance_pct=tolerance_pct)
    if po["status"] != "approved":
        return _result("REVIEW", f"{po['po_number']} is marked {po['status']}, so it cannot support automatic approval.", ["PO_NOT_APPROVED"], invoice, po,
                       next_step="Wait for procurement to approve the PO or select an approved one.", tolerance_pct=tolerance_pct)
    if not invoice.currency:
        return _result("REVIEW", "The invoice currency couldn't be established with confidence.", ["CURRENCY_UNKNOWN"], invoice, po,
                       next_step="Confirm the currency on the source document.", tolerance_pct=tolerance_pct)
    if invoice.currency != po["currency"]:
        return _result("REVIEW", f"Currency mismatch: invoice is {invoice.currency}; {po['po_number']} is {po['currency']}.", ["CURRENCY_MISMATCH"], invoice, po,
                       next_step="Ask AP to confirm the PO currency or correct the invoice record.", tolerance_pct=tolerance_pct)
    variance = round(invoice.total - po["approved_amount"], 2)
    pct = abs(variance) / po["approved_amount"] * 100
    prior = _previous_approved_billing(po["po_number"])
    cumulative = prior + invoice.total
    cap = po["approved_amount"] * (1 + tolerance_pct / 100)
    if invoice.total > cap:
        if prior > 0 and cumulative > cap:
            excess = cumulative - po["approved_amount"]
            return _result("REVIEW", f"Including previously approved invoices ({po['currency']} {prior:,.2f}), billed value would reach {po['currency']} {cumulative:,.2f}, above the PO by {po['currency']} {excess:,.2f}.", ["CUMULATIVE_PO_OVERAGE"], invoice, po, variance,
                           next_step="Check prior invoice history and remaining PO balance before approving this bill.", tolerance_pct=tolerance_pct)
        return _result("REVIEW", f"The invoice is {po['currency']} {variance:,.2f} ({pct:.1f}%) above the PO, beyond the {tolerance_pct:.1f}% tolerance.", ["OVER_PO_TOLERANCE"], invoice, po, variance,
                       next_step="Request a PO amendment or an authorized exception before payment.", tolerance_pct=tolerance_pct)
    if cumulative > cap and prior > 0:
        excess = cumulative - po["approved_amount"]
        return _result("REVIEW", f"Including previously approved invoices ({po['currency']} {prior:,.2f}), billed value would reach {po['currency']} {cumulative:,.2f}, above the PO by {po['currency']} {excess:,.2f}.", ["CUMULATIVE_PO_OVERAGE"], invoice, po, variance,
                       next_step="Check prior invoice history and remaining PO balance before approving this bill.", tolerance_pct=tolerance_pct)
    if variance < -0.02:
        remaining = max(0.0, po["approved_amount"] - cumulative)
        return _result("REVIEW", f"This invoice is {po['currency']} {abs(variance):,.2f} below the PO. It may be a legitimate split bill; {po['currency']} {remaining:,.2f} would remain after it.", ["POSSIBLE_SPLIT_BILL"], invoice, po, variance,
                       next_step="Confirm the delivered work and remaining PO balance; split bills stay human-reviewed.", tolerance_pct=tolerance_pct)
    flags = ["WITHIN_TOLERANCE"] if variance > 0.02 else []
    reason = "Supplier, PO, currency, duplicate, and total checks all look good." if not flags else f"Supplier and PO match. The {pct:.1f}% overage is within the configured {tolerance_pct:.1f}% tolerance."
    if prior:
        reason += f" Prior approved billing is {po['currency']} {prior:,.2f}; cumulative billed value remains within the PO."
    return _result("APPROVE", reason, flags, invoice, po, variance,
                   next_step="Ready for AP approval under this demo policy; payment is not initiated.", tolerance_pct=tolerance_pct)


def process_pdf(pdf_bytes: bytes, filename: str, pos: list[dict[str, Any]], tolerance_pct: float = 2.0) -> tuple[Invoice, dict[str, Any]]:
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    invoice = parse_invoice(extract_text(pdf_bytes), filename, digest)
    return invoice, decide(invoice, pos, tolerance_pct)


def save_run(invoice: Invoice, result: dict[str, Any]) -> int:
    init_db()
    po = result.get("matched_po") or {}
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=10000")
        cursor = conn.execute("""INSERT INTO runs(created_at,filename,sha256,invoice_json,result_json,
            invoice_number_norm,vendor_norm,po_number,total,decision) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), invoice.source, invoice.sha256,
             json.dumps(asdict(invoice), ensure_ascii=False), json.dumps(result, ensure_ascii=False),
             _normalize(invoice.invoice_number), _normalize(invoice.vendor), po.get("po_number") or invoice.po_number,
             invoice.total, result["decision"]))
        run_id = int(cursor.lastrowid)
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO case_meta(run_id,status,assigned_to,corrections_json,updated_at) VALUES(?,?,?,?,?)",
                     (run_id,"NEW","","{}",created_at))
        conn.execute("INSERT INTO case_events(run_id,kind,message,payload_json,created_at) VALUES(?,?,?,?,?)",
                     (run_id,"created",f"Review created · {result['decision']} recommendation.","{}",created_at))
        return run_id


def get_runs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    init_db()
    limit, offset = max(1, min(int(limit), 1000)), max(0, int(offset))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("""SELECT r.id,r.created_at,r.filename,r.invoice_json,r.result_json,
            COALESCE(m.status,'NEW'),COALESCE(m.assigned_to,''),COALESCE(m.updated_at,r.created_at),
            COALESCE(m.decision_override,''),COALESCE(m.override_rationale,'')
            FROM runs r LEFT JOIN case_meta m ON m.run_id=r.id ORDER BY r.id DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    runs = []
    for row in rows:
        invoice = json.loads(row[3])
        invoice.pop("raw_text", None)
        runs.append({"id":row[0], "created_at":row[1], "filename":row[2], "invoice":invoice, "result":json.loads(row[4]),
                     "status":row[5],"assigned_to":row[6],"updated_at":row[7],
                     "decision_override":row[8],"override_rationale":row[9]})
    return runs


def get_summary() -> dict[str, Any]:
    init_db()
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=6)
    daily = {start + timedelta(days=i):{"date":(start + timedelta(days=i)).isoformat(), "total":0, "approved":0, "review":0, "rejected":0} for i in range(7)}
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT created_at,decision,total FROM runs").fetchall()
        case_rows = conn.execute("SELECT status,corrections_json,decision_override FROM case_meta").fetchall()
    counts = {"total":len(rows), "approved":0, "review":0, "rejected":0}
    for created_at, decision, amount in rows:
        key = {"APPROVE":"approved", "REVIEW":"review", "REJECT":"rejected"}.get(decision)
        if key:
            counts[key] += 1
        try:
            day = datetime.fromisoformat(created_at).date()
            if day in daily:
                daily[day]["total"] += 1
                if key:
                    daily[day][key] += 1
        except (TypeError, ValueError):
            continue
    feedback = sum(len(json.loads(corrections or "{}")) for _,corrections,_ in case_rows)
    overrides = sum(bool(override) for _,_,override in case_rows)
    open_cases = sum(status != "RESOLVED" for status,_,_ in case_rows)
    return {**counts, "feedback":feedback,"overrides":overrides,"open_cases":open_cases,
            "daily":list(daily.values()), "recent":get_runs(limit=5)}
