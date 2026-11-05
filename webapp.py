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

from asa_engine import DB_PATH, ROOT, get_case, get_runs, get_summary, init_db, load_pos, process_pdf, save_run, update_case

WEB_ROOT = ROOT / "frontend"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
DEFAULT_TOLERANCE = 2.0
PROCESS_LOCK = threading.RLock()


class MosaicHandler(BaseHTTPRequestHandler):
    server_version = "MosaicAP/1.0"

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            host = os.getenv("HOST", "127.0.0.1")
            port = int(os.getenv("PORT", "8501"))
            return self._json(200, {
                "ok": True,
                "service": "Mosaic AP",
                "local_only": host in {"127.0.0.1", "localhost", "::1"},
                "host": host,
                "port": port,
                "reset_db_on_start": os.getenv("RESET_DB_ON_START", "false").lower() in {"1", "true", "yes", "on"},
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
                ("happy_path.pdf", "Clean match", "All core evidence aligns", "approve"),
                ("within_tolerance.pdf", "A little over", "Within the 2% guardrail", "approve"),
                ("cumulative_balance.pdf", "The PO is nearly spoken for", "Run the clean match first · check the remaining balance", "review"),
                ("possible_split_invoice.pdf", "Possible split bill", "Below PO; check delivered work", "review"),
                ("vendor_mismatch.pdf", "Different supplier", "Supplier and PO owner disagree", "stop"),
                ("missing_po_reference.pdf", "No PO reference", "Find the right commitment", "review"),
                ("over_tolerance.pdf", "Outside tolerance", "Needs an exception or amendment", "review"),
                ("missing_total.pdf", "Total not found", "Never guess a payable amount", "review"),
                ("cents_mismatch.pdf", "Invoice math does not tie", "Subtotal and tax disagree with total", "review"),
                ("ambiguous_date.pdf", "Date needs a locale", "Two readings are possible · Mosaic will not guess", "review"),
                ("future_date.pdf", "Date is in the future", "Confirm the supplier document date", "review"),
                ("supplier_name_variant.pdf", "Supplier name variation", "Similar names are a lead, not a match", "review"),
                ("pending_po.pdf", "PO is not approved", "Procurement status is part of the control", "review"),
                ("currency_unknown.pdf", "Currency is not stated", "No default currency is assumed", "review"),
                ("po_typo.pdf", "PO reference has a typo", "A ranked lead is shown · never auto-selected", "review"),
                ("image_only_scan.pdf", "Image-only scan", "No text is guessed from a scan", "review"),
            ]
            available = {p.name for p in (ROOT / "data" / "invoices").glob("*.pdf")}
            return self._json(200, [{"file": f, "title": t, "note": n, "kind": k} for f, t, n, k in cases if f in available])
        if parsed.path == "/api/pos":
            return self._json(200, load_pos())
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
            search = query.get("q", [""])[0].casefold().strip()
            cases = get_runs(limit=1000)
            if status in {"NEW", "IN_REVIEW", "WAITING", "RESOLVED"}:
                cases = [case for case in cases if case["status"] == status]
            if decision in {"APPROVE", "REVIEW", "REJECT"}:
                cases = [case for case in cases if case["result"]["decision"] == decision]
            if search:
                cases = [case for case in cases if search in " ".join([case["filename"],case["invoice"].get("invoice_number") or "",case["invoice"].get("vendor") or "",case["result"]["decision"],case["status"]]).casefold()]
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

    def _serve(self, path: Path) -> None:
        if not path.is_file() or path.parent.resolve() != WEB_ROOT.resolve():
            return self._json(404, {"error":"Asset not found"})
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), f"{kind}; charset=utf-8" if kind.startswith("text/") or "javascript" in kind else kind)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
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
            self._json(200, {"id":run_id, "created_at":self._created_at(run_id), "invoice":asdict(invoice), "result":result,
                             "case":get_case(run_id)})
        except Exception as exc:
            self._json(422, {"error":f"I couldn't read this invoice safely: {exc}"})

    def do_PATCH(self) -> None:
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
        with sqlite3.connect(DB_PATH) as conn:
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
    print("\n  MOSAIC AP  /  INVOICE REVIEW")
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




