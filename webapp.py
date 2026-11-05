from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import threading
from dataclasses import asdict
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from asa_engine import (
    DB_PATH, ROOT, ask_assistant, get_active_db_path, get_case, get_runs,
    get_session_db_path, get_summary, init_db, load_grns, load_po_lines,
    load_pos, load_vendors, get_vendor_by_name, process_pdf,
    reset_active_db_path, save_run, seed_database, set_active_db_path, update_case
)

WEB_ROOT = ROOT / "frontend"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
DEFAULT_TOLERANCE = 2.0
PROCESS_LOCK = threading.RLock()


class MosaicHandler(BaseHTTPRequestHandler):
    server_version = "MosaicAP/2.0-Enterprise"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.log_date_time_string()} | {fmt % args}")

    def _send(self, status: int, payload: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: object) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _setup_session(self) -> tuple[str | None, Any]:
        headers = getattr(self, "headers", None)
        session_id = headers.get("X-Session-ID") if headers else None
        if not session_id:
            path = getattr(self, "path", "")
            parsed = urlparse(path)
            qs = parse_qs(parsed.query)
            session_id = qs.get("session", [None])[0]
        db_path = get_session_db_path(session_id)
        token = set_active_db_path(db_path)
        return session_id, token

    def do_GET(self) -> None:
        session_id, token = self._setup_session()
        try:
            self._handle_GET()
        finally:
            reset_active_db_path(token)

    def _handle_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            host = os.getenv("HOST", "127.0.0.1")
            port = int(os.getenv("PORT", "8501"))
            return self._json(200, {
                "ok": True,
                "service": "Mosaic AP Enterprise",
                "version": "2.0.0",
                "local_only": host in {"127.0.0.1", "localhost", "::1"},
                "host": host,
                "port": port,
                "features": {
                    "three_way_matching": True,
                    "risk_scoring_engine": True,
                    "vendor_intelligence": True,
                    "ai_review_assistant": True,
                    "approval_tiers": True,
                    "audit_trail": True
                },
                "reset_db_on_start": os.getenv("RESET_DB_ON_START", "false").lower() in {"1", "true", "yes", "on"},
            })

        if parsed.path == "/api/session/status":
            session_id = self.headers.get("X-Session-ID")
            return self._json(200, {
                "session_id": session_id or "default",
                "isolated": bool(session_id),
                "summary": get_summary()
            })

        if parsed.path.startswith("/api/sample/"):
            filename = unquote(parsed.path.removeprefix("/api/sample/"))
            samples_dir = (ROOT / "data" / "invoices").resolve()
            sample_path = (samples_dir / filename).resolve()
            if Path(filename).name != filename or Path(filename).suffix.lower() != ".pdf" or sample_path.parent != samples_dir:
                return self._json(400, {"error":"Choose a prepared PDF sample."})
            if not sample_path.is_file():
                return self._json(404, {"error":"That prepared PDF is not available."})
            return self._send(200, sample_path.read_bytes(), "application/pdf")

        if parsed.path == "/api/samples":
            cases = [
                ("happy_path.pdf", "Clean 3-Way Match", "All PO lines & GRN receiving reconcile", "approve"),
                ("quantity_mismatch.pdf", "3-Way Quantity Mismatch", "Invoiced exceeds goods received (GRN)", "review"),
                ("duplicate_invoice.pdf", "Duplicate Submission", "Cryptographic fingerprint duplicate", "stop"),
                ("within_tolerance.pdf", "A little over", "Within the 2% guardrail", "approve"),
                ("cumulative_balance.pdf", "The PO is nearly spoken for", "Cumulative billing cap exceeded", "review"),
                ("possible_split_invoice.pdf", "Possible split bill", "Below PO; valid partial delivery", "review"),
                ("vendor_mismatch.pdf", "Different supplier", "Supplier and PO owner disagree", "stop"),
                ("missing_po_reference.pdf", "No PO reference", "Find the right commitment", "review"),
                ("over_tolerance.pdf", "Outside tolerance", "Needs an exception or amendment", "review"),
                ("missing_total.pdf", "Total not found", "Never guess a payable amount", "review"),
                ("cents_mismatch.pdf", "Invoice math does not tie", "Subtotal and tax disagree with total", "review"),
                ("ambiguous_date.pdf", "Date needs a locale", "Two readings are possible · no guessing", "review"),
                ("future_date.pdf", "Date is in the future", "Confirm supplier document date", "review"),
                ("supplier_name_variant.pdf", "Supplier name variation", "Similar names are a lead, not a match", "review"),
                ("pending_po.pdf", "PO is not approved", "Procurement status pending", "review"),
                ("currency_unknown.pdf", "Currency is not stated", "No default currency assumed", "review"),
                ("po_typo.pdf", "PO reference has a typo", "A ranked lead is shown · never auto-selected", "review"),
                ("image_only_scan.pdf", "Image-only scan", "No text layer · OCR pipeline needed", "review"),
            ]
            available = {p.name for p in (ROOT / "data" / "invoices").glob("*.pdf")}
            return self._json(200, [{"file": f, "title": t, "note": n, "kind": k} for f, t, n, k in cases if f in available])

        if parsed.path == "/api/pos":
            return self._json(200, load_pos())

        if parsed.path == "/api/grns":
            return self._json(200, load_grns())

        if parsed.path == "/api/vendors":
            return self._json(200, load_vendors())

        if parsed.path.startswith("/api/vendors/"):
            vendor_key = unquote(parsed.path.removeprefix("/api/vendors/")).strip()
            vendor = get_vendor_by_name(vendor_key)
            if not vendor:
                vendors = load_vendors()
                vendor = next((v for v in vendors if v.get("vendor_id") == vendor_key), None)
            return self._json(200, vendor) if vendor else self._json(404, {"error": "Vendor not found in master records."})

        if parsed.path == "/api/notifications":
            cases = get_runs(limit=100)
            critical = [c for c in cases if c.get("priority") == "CRITICAL" or c.get("result", {}).get("risk_engine", {}).get("level") == "CRITICAL"]
            unassigned = [c for c in cases if not c.get("assigned_to") and c.get("status") != "RESOLVED"]
            mismatches = [c for c in cases if c.get("result", {}).get("three_way_match", {}).get("has_quantity_mismatch")]
            return self._json(200, {
                "unread_count": len(critical) + len(unassigned[:5]),
                "critical_cases": [{"id": c["id"], "vendor": c["invoice"].get("vendor"), "amount": c["invoice"].get("total"), "reason": c["result"].get("reason")} for c in critical[:5]],
                "unassigned_cases": [{"id": c["id"], "vendor": c["invoice"].get("vendor"), "amount": c["invoice"].get("total")} for c in unassigned[:5]],
                "three_way_exceptions": len(mismatches)
            })

        if parsed.path.startswith("/api/report/"):
            try:
                run_id = int(parsed.path.rsplit("/", 1)[1])
            except ValueError:
                return self._json(400, {"error":"Invalid case ID"})
            case = get_case(run_id)
            if not case:
                return self._json(404, {"error":"Case not found"})
            return self._serve_report_html(case)

        if parsed.path == "/api/summary":
            return self._json(200, get_summary())

        if parsed.path == "/api/runs":
            query = parse_qs(parsed.query)
            status = query.get("status", [""])[0].upper()
            search = query.get("q", [""])[0].casefold().strip()
            try:
                limit = min(max(int(query.get("limit", ["1000"])[0]), 1), 1000)
                offset = max(int(query.get("offset", ["0"])[0]), 0)
            except ValueError:
                return self._json(400, {"error":"Invalid history page."})
            runs = get_runs(limit=limit, offset=offset)
            if status in {"APPROVE", "REVIEW", "REJECT"}:
                runs = [r for r in runs if r["result"]["decision"] == status]
            if search:
                runs = [r for r in runs if search in " ".join([r["filename"], r["invoice"].get("invoice_number") or "", r["invoice"].get("vendor") or "", r["result"]["decision"]]).casefold()]
            return self._json(200, runs)

        if parsed.path == "/api/cases":
            query = parse_qs(parsed.query)
            status = query.get("status", [""])[0].upper()
            decision = query.get("decision", [""])[0].upper()
            priority = query.get("priority", [""])[0].upper()
            search = query.get("q", [""])[0].casefold().strip()
            cases = get_runs(limit=1000)

            if status == "OPEN":
                cases = [case for case in cases if case["status"] != "RESOLVED"]
            elif status in {"NEW", "IN_REVIEW", "WAITING", "ESCALATED", "RESOLVED"}:
                cases = [case for case in cases if case["status"] == status]

            if decision in {"APPROVE", "REVIEW", "REJECT"}:
                cases = [case for case in cases if case["result"]["decision"] == decision]

            if priority in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
                cases = [case for case in cases if case.get("priority") == priority]

            if search:
                cases = [case for case in cases if search in " ".join([
                    f"AP-{str(case['id']).zfill(6)}",
                    case["filename"],
                    case["invoice"].get("invoice_number") or "",
                    case["invoice"].get("vendor") or "",
                    case["result"]["decision"],
                    case["status"],
                    case.get("assigned_to") or "",
                    case.get("priority") or ""
                ]).casefold()]
            return self._json(200, cases)

        if parsed.path.startswith("/api/cases/"):
            try:
                run_id = int(parsed.path.rsplit("/", 1)[1])
            except ValueError:
                return self._json(400, {"error":"Invalid case number."})
            case = get_case(run_id)
            return self._json(200, case) if case else self._json(404, {"error":"Case not found."})

        if parsed.path == "/":
            return self._serve(WEB_ROOT / "index.html")

        if parsed.path in {"/styles.css", "/app.js"}:
            return self._serve(WEB_ROOT / parsed.path.lstrip("/"))

        return self._json(404, {"error":"Not found"})

    def _serve_report_html(self, case: dict[str, Any]) -> None:
        invoice = case.get("invoice", {})
        result = case.get("result", {})
        po = result.get("matched_po") or {}
        tw = result.get("three_way_match") or {}
        risk = result.get("risk_engine") or {}
        events = case.get("events", [])
        case_code = f"AP-{str(case['id']).zfill(6)}"

        lines_html = "".join([f"""<tr>
            <td>{l.get('sku', '—')}</td>
            <td>{l.get('description', '—')}</td>
            <td>{l.get('ordered_qty', 0):g}</td>
            <td>{l.get('received_qty', 0):g}</td>
            <td>{l.get('invoiced_qty', 0):g}</td>
            <td>${l.get('po_unit_price', 0):,.2f}</td>
            <td>${l.get('invoiced_unit_price', 0):,.2f}</td>
            <td>${l.get('line_total', 0):,.2f}</td>
            <td><span class="badge badge-{l.get('line_status', '').lower()}">{l.get('line_status')}</span></td>
        </tr>""" for l in tw.get("lines", [])])

        events_html = "".join([f"""<div class="event-item">
            <span class="event-time">{e.get('created_at', '')[:19].replace('T', ' ')}</span>
            <b>{e.get('kind', '').title()}:</b> {e.get('message', '')}
        </div>""" for e in events])

        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mosaic AP — Audit & Review Dossier {case_code}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a; margin: 0; padding: 32px; background: #fff; line-height: 1.5; }}
    .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #059669; padding-bottom: 20px; margin-bottom: 28px; }}
    .brand {{ font-size: 22px; font-weight: 800; color: #059669; letter-spacing: -0.5px; }}
    .brand span {{ color: #0f172a; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .badge-approve, .badge-match {{ background: #dcfce7; color: #15803d; }}
    .badge-review, .badge-qty_exceeds_grn, .badge-price_mismatch {{ background: #fef3c7; color: #b45309; }}
    .badge-reject, .badge-unordered_item {{ background: #fee2e2; color: #b91c1c; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }}
    .card small {{ display: block; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 4px; }}
    .card b {{ font-size: 15px; color: #0f172a; }}
    h3 {{ font-size: 16px; font-weight: 700; margin: 24px 0 12px 0; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
    th, td {{ padding: 8px 10px; border: 1px solid #e2e8f0; text-align: left; }}
    th {{ background: #f1f5f9; font-weight: 700; color: #475569; }}
    .event-item {{ font-size: 12px; margin-bottom: 8px; }}
    .event-time {{ color: #64748b; font-family: monospace; margin-right: 8px; }}
    .sign-off {{ margin-top: 40px; border-top: 1px dashed #cbd5e1; padding-top: 20px; display: flex; justify-content: space-between; }}
    .sign-box {{ width: 30%; border-bottom: 1px solid #000; height: 35px; }}
    @media print {{ body {{ padding: 0; }} }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="brand">Mosaic <span>AP Enterprise</span></div>
      <div style="font-size: 13px; color: #64748b;">Automated Invoice Review & Audit Dossier</div>
    </div>
    <div style="text-align: right;">
      <div style="font-size: 18px; font-weight: 800;">{case_code}</div>
      <span class="badge badge-{result.get('decision', '').lower()}">{result.get('decision')}</span>
    </div>
  </div>

  <div class="grid">
    <div class="card"><small>Supplier</small><b>{invoice.get('vendor') or 'Not identified'}</b></div>
    <div class="card"><small>Invoice Reference</small><b>{invoice.get('invoice_number') or 'None'}</b></div>
    <div class="card"><small>Invoice Amount</small><b>{invoice.get('currency', 'USD')} {invoice.get('total', 0):,.2f}</b></div>
    <div class="card"><small>Risk Rating</small><b>{risk.get('score', 0)}/100 ({risk.get('level', 'LOW')})</b></div>
    <div class="card"><small>PO Commitment</small><b>{po.get('po_number') or 'No PO'}</b></div>
    <div class="card"><small>3-Way Match Status</small><b>{tw.get('status_label', 'Evaluated')}</b></div>
    <div class="card"><small>Review Status</small><b>{case.get('status', 'NEW')}</b></div>
    <div class="card"><small>Approval Tier</small><b>{risk.get('approval_tier', 'Tier 1')}</b></div>
  </div>

  <h3>Three-Way Match Line Reconciliation</h3>
  <table>
    <thead>
      <tr><th>SKU</th><th>Description</th><th>PO Qty</th><th>GRN Qty</th><th>Inv Qty</th><th>PO Price</th><th>Inv Price</th><th>Line Total</th><th>Status</th></tr>
    </thead>
    <tbody>
      {lines_html or '<tr><td colspan="9" style="text-align:center; color:#64748b;">No line item records</td></tr>'}
    </tbody>
  </table>

  <h3>Explainable Risk Assessment & Discrepancies</h3>
  <p><b>Model Recommendation:</b> {result.get('reason')}</p>
  <p><b>Recommended Action:</b> {result.get('next_step')}</p>

  <h3>Audit & Compliance Trail</h3>
  <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;">
    {events_html or '<div>No audit events recorded.</div>'}
  </div>

  <div class="sign-off">
    <div><small>Prepared by Reviewer</small><div class="sign-box"></div></div>
    <div><small>AP Supervisor Approval</small><div class="sign-box"></div></div>
    <div><small>Date Authorized</small><div class="sign-box"></div></div>
  </div>
</body>
</html>"""
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _serve(self, path: Path) -> None:
        if not path.is_file() or path.parent.resolve() != WEB_ROOT.resolve():
            return self._json(404, {"error":"Asset not found"})
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), f"{kind}; charset=utf-8" if kind.startswith("text/") or "javascript" in kind else kind)

    def do_POST(self) -> None:
        session_id, token = self._setup_session()
        try:
            self._handle_POST()
        finally:
            reset_active_db_path(token)

    def _handle_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/session/reset":
            session_id = self.headers.get("X-Session-ID")
            target_db = get_session_db_path(session_id)
            try:
                target_db.unlink(missing_ok=True)
            except Exception:
                pass
            init_db(target_db)
            return self._json(200, {
                "ok": True,
                "session_id": session_id or "default",
                "message": "Workspace cleared to a clean slate (0 cases)."
            })

        if parsed.path == "/api/session/seed":
            session_id = self.headers.get("X-Session-ID")
            target_db = get_session_db_path(session_id)
            init_db(target_db)
            seed_database(target_db)
            return self._json(200, {
                "ok": True,
                "session_id": session_id or "default",
                "message": "Demo dataset loaded with 3 active exceptions and 3 resolved cases."
            })

        if parsed.path == "/api/assistant":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 32_768:
                    return self._json(400, {"error": "Invalid request body length."})
                payload = json.loads(self.rfile.read(length))
                case_id = int(payload.get("case_id", 0))
                query = str(payload.get("query", "")).strip()
                if not case_id or not query:
                    return self._json(400, {"error": "Provide case_id and query string."})
                res = ask_assistant(case_id, query)
                return self._json(200, res)
            except Exception as exc:
                return self._json(500, {"error": f"Assistant query error: {exc}"})

        if parsed.path == "/api/grns/import":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, list):
                    return self._json(400, {"error": "GRN import payload must be a list of records."})
                with (ROOT / "data" / "goods_receipts" / "goods_receipts.json").open("w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                return self._json(200, {"ok": True, "count": len(payload)})
            except Exception as exc:
                return self._json(400, {"error": f"GRN import failed: {exc}"})

        if parsed.path not in {"/api/review", "/api/upload"}:
            return self._json(404, {"error":"Not found"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"error":"Invalid content length"})

        if length <= 0 or length > MAX_UPLOAD_BYTES + 1024 * 32:
            return self._json(413, {"error":"Add a PDF under 15 MB to continue."})

        body = self.rfile.read(length)
        if parsed.path == "/api/review":
            query = parse_qs(parsed.query)
            filename = Path(unquote(query.get("sample", [""])[0])).name
            samples_dir = ROOT / "data" / "invoices"
            if not filename.endswith(".pdf") or not (samples_dir / filename).is_file():
                return self._json(400, {"error":"Choose one of the prepared invoice scenarios."})
            pdf_bytes = (samples_dir / filename).read_bytes()
        else:
            pdf_bytes, filename = self._read_upload(body)
            if pdf_bytes is None:
                return self._json(400, {"error":filename})

        if len(pdf_bytes) > MAX_UPLOAD_BYTES:
            return self._json(413, {"error":"The PDF is over the 15 MB demo limit."})
        if not pdf_bytes.lstrip().startswith(b"%PDF-"):
            return self._json(400, {"error":"That file does not look like a valid PDF. Please choose a PDF invoice."})

        try:
            params = parse_qs(parsed.query)
            tolerance = float(params.get("tolerance", [str(DEFAULT_TOLERANCE)])[0])
            tolerance = min(max(tolerance, 0), 10)
            with PROCESS_LOCK:
                invoice, result = process_pdf(pdf_bytes, filename, load_pos(), tolerance)
                run_id = save_run(invoice, result)
            self._json(200, {
                "id": run_id,
                "created_at": self._created_at(run_id),
                "invoice": asdict(invoice),
                "result": result,
                "case": get_case(run_id)
            })
        except Exception as exc:
            self._json(422, {"error":f"I couldn't read this invoice safely: {exc}"})

    def do_PATCH(self) -> None:
        session_id, token = self._setup_session()
        try:
            self._handle_PATCH()
        finally:
            reset_active_db_path(token)

    def _handle_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/cases/"):
            return self._json(404, {"error":"Not found"})
        try:
            run_id = int(parsed.path.rsplit("/", 1)[1])
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"error":"Invalid case update."})
        if length <= 0 or length > 16_384:
            return self._json(413, {"error":"Case updates must be under 16 KB."})
        try:
            changes = json.loads(self.rfile.read(length))
            if not isinstance(changes, dict):
                raise ValueError("Case update must be an object.")
            case = update_case(run_id, changes)
            if case is None:
                return self._json(404, {"error":"Case not found."})
            return self._json(200, case)
        except (json.JSONDecodeError, ValueError) as exc:
            return self._json(400, {"error":str(exc) or "Invalid case update."})
        except Exception as exc:
            return self._json(500, {"error":f"Case update failed: {exc}"})

    @staticmethod
    def _created_at(run_id: int) -> str:
        with sqlite3.connect(get_active_db_path()) as conn:
            row = conn.execute("SELECT created_at FROM runs WHERE id=?", (run_id,)).fetchone()
        return row[0] if row else ""

    def _read_upload(self, body: bytes) -> tuple[bytes | None, str]:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return None, "Choose a PDF from your device to upload."
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                b"MIME-Version: 1.0\r\nContent-Type: " + content_type.encode("ascii") + b"\r\n\r\n" + body
            )
            for part in message.iter_parts():
                if part.get_content_disposition() == "form-data" and part.get_param("name", header="content-disposition") == "invoice":
                    return part.get_payload(decode=True), Path(part.get_filename() or "invoice.pdf").name
        except Exception:
            pass
        return None, "The upload could not be read. Please try selecting the PDF again."


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8501"))
    reset_db_on_start = os.getenv("RESET_DB_ON_START", "false").lower() in {"1", "true", "yes", "on"}

    if reset_db_on_start:
        try:
            DB_PATH.unlink()
        except FileNotFoundError:
            pass
        except IsADirectoryError:
            pass
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    init_db()
    server = ThreadingHTTPServer((host, port), MosaicHandler)
    print("\n  MOSAIC AP ENTERPRISE  /  INTELLIGENT INVOICE REVIEW")
    print(f"  Host: {host}")
    print(f"  Local preview: http://localhost:{port}")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"  Public bind: http://{host}:{port}")
    print(f"  Reset DB on start: {reset_db_on_start}")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Mosaic stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
