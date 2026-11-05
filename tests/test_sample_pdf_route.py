from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock

from webapp import MosaicHandler


class SamplePdfRouteTests(TestCase):
    def request(self, path):
        handler = MosaicHandler.__new__(MosaicHandler)
        handler.path = path
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_GET()
        return handler

    def test_prepared_pdf_is_served_inline_as_pdf(self):
        handler = self.request("/api/sample/happy_path.pdf")
        handler.send_response.assert_called_once_with(200)
        headers = {call.args[0]: call.args[1] for call in handler.send_header.call_args_list}
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertTrue(handler.wfile.getvalue().startswith(b"%PDF-"))

    def test_sample_route_rejects_path_traversal(self):
        handler = self.request("/api/sample/%2e%2e%2fREADME.md")
        handler.send_response.assert_called_once_with(400)
        self.assertIn(b"prepared PDF", handler.wfile.getvalue())
