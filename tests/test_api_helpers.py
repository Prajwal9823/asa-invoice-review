import unittest
from email.message import Message
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
