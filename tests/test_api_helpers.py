import json
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import asa_engine as engine
import webapp


class UploadParserTests(unittest.TestCase):
    def test_multipart_invoice_field_is_parsed_as_pdf_bytes(self) -> None:
        boundary = "mosaic-unit-boundary"
        payload = b"%PDF-1.4\ncontent"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"invoice\"; filename=\"sample.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode()
                + payload + f"\r\n--{boundary}--\r\n".encode())
        handler = object.__new__(webapp.MosaicHandler)
        handler.headers = Message()
        handler.headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        parsed, filename = handler._read_upload(body)
        self.assertEqual(parsed, payload)
        self.assertEqual(filename, "sample.pdf")

    def test_non_multipart_upload_is_rejected(self) -> None:
        handler = object.__new__(webapp.MosaicHandler)
        handler.headers = Message()
        handler.headers["Content-Type"] = "application/json"
        payload, message = handler._read_upload(b"{}")
        self.assertIsNone(payload)
        self.assertIn("PDF", message)


class WebApiEndpointTests(unittest.TestCase):
    def _mock_get(self, path: str):
        handler = webapp.MosaicHandler.__new__(webapp.MosaicHandler)
        handler.path = path
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_GET()
        return handler

    def _mock_post(self, path: str, body_bytes: bytes, content_type: str = "application/json"):
        handler = webapp.MosaicHandler.__new__(webapp.MosaicHandler)
        handler.path = path
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body_bytes))
        handler.headers["Content-Type"] = content_type
        handler.rfile = BytesIO(body_bytes)
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_POST()
        return handler

    def _mock_patch(self, path: str, body_bytes: bytes):
        handler = webapp.MosaicHandler.__new__(webapp.MosaicHandler)
        handler.path = path
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body_bytes))
        handler.headers["Content-Type"] = "application/json"
        handler.rfile = BytesIO(body_bytes)
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_PATCH()
        return handler

    def test_health_endpoint_reports_enterprise_features(self) -> None:
        handler = self._mock_get("/api/health")
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue().decode())
        self.assertTrue(data["ok"])
        self.assertTrue(data["features"]["three_way_matching"])
        self.assertTrue(data["features"]["risk_scoring_engine"])
        self.assertTrue(data["features"]["vendor_intelligence"])

    def test_grns_endpoint_returns_receipts(self) -> None:
        handler = self._mock_get("/api/grns")
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue().decode())
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 4)
        self.assertIn("grn_number", data[0])

    def test_vendors_endpoint_returns_master_records(self) -> None:
        handler = self._mock_get("/api/vendors")
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue().decode())
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 5)
        self.assertIn("bank_details", data[0])

    def test_vendor_single_lookup(self) -> None:
        handler = self._mock_get("/api/vendors/Northstar%20Office%20Supply")
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue().decode())
        self.assertEqual(data["name"], "Northstar Office Supply")

    def test_notifications_endpoint(self) -> None:
        handler = self._mock_get("/api/notifications")
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue().decode())
        self.assertIn("unread_count", data)

    def test_report_endpoint_serves_html(self) -> None:
        # Create a run first
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        inv, res = engine.process_pdf(path.read_bytes(), "happy_path.pdf", engine.load_pos())
        run_id = engine.save_run(inv, res)

        handler = self._mock_get(f"/api/report/{run_id}")
        handler.send_response.assert_called_once_with(200)
        html = handler.wfile.getvalue().decode()
        self.assertIn("Mosaic", html)
        self.assertIn(f"AP-{str(run_id).zfill(6)}", html)

    def test_assistant_endpoint(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        inv, res = engine.process_pdf(path.read_bytes(), "happy_path.pdf", engine.load_pos())
        run_id = engine.save_run(inv, res)

        body = json.dumps({"case_id": run_id, "query": "Why was this invoice approved?"}).encode()
        handler = self._mock_post("/api/assistant", body)
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue().decode())
        self.assertIn("answer", data)
        self.assertIn("citations", data)


if __name__ == "__main__":
    unittest.main()
