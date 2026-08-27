# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

import asyncio
from io import BytesIO
from unittest import TestCase
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientError
from pypdf import PdfWriter

from neuro_san_studio.coded_tools.utils.safe_fetch import SafeFetch
from tests.neuro_san_studio.coded_tools.utils.safe_fetch.helpers import make_stream_session


def make_pdf_bytes(pages: int = 1) -> bytes:
    """Build a minimal valid PDF with the given number of blank pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class TestFetchPdf(TestCase):
    """Unit tests for SafeFetch.fetch_pdf_text."""

    def _call(self, url: str, session) -> str:
        """Invoke fetch_pdf_text with the given URL and session."""
        return asyncio.run(SafeFetch.fetch_pdf_text(url, session))

    def test_returns_joined_page_text(self):
        """Tests that text from all PDF pages is joined into a single newline-separated string."""
        pages = [MagicMock(), MagicMock()]
        pages[0].extract_text.return_value = "Page one"
        pages[1].extract_text.return_value = "Page two"
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with (
            patch.object(SafeFetch, "download_pdf_bytes", new=AsyncMock(return_value=b"%PDF-fake")),
            patch("neuro_san_studio.coded_tools.utils.pdf_utils.PdfReader", return_value=mock_reader),
        ):
            result = self._call("http://example.com/doc.pdf", MagicMock())

        self.assertEqual(result, "Page one\nPage two")

    def test_none_page_text_coerced_to_empty(self):
        """Tests that a page whose extract_text() returns None is treated as empty text."""
        pages = [MagicMock(), MagicMock(), MagicMock()]
        pages[0].extract_text.return_value = "Page one"
        pages[1].extract_text.return_value = None
        pages[2].extract_text.return_value = "Page three"
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with (
            patch.object(SafeFetch, "download_pdf_bytes", new=AsyncMock(return_value=b"%PDF-fake")),
            patch("neuro_san_studio.coded_tools.utils.pdf_utils.PdfReader", return_value=mock_reader),
        ):
            result = self._call("http://example.com/doc.pdf", MagicMock())

        self.assertEqual(result, "Page one\n\nPage three")

    def test_real_pdf_bytes_parse_successfully(self):
        """Tests that genuine PDF bytes are parsed by real pypdf without errors."""
        data = make_pdf_bytes(pages=2)
        with patch.object(SafeFetch, "download_pdf_bytes", new=AsyncMock(return_value=data)):
            result = self._call("http://example.com/doc.pdf", MagicMock())
        self.assertIsInstance(result, str)

    def test_invalid_pdf_bytes_raise_client_error_with_prefix(self):
        """Tests that unparseable PDF bytes raise ClientError with url_not_accessible prefix."""
        with patch.object(SafeFetch, "download_pdf_bytes", new=AsyncMock(return_value=b"not a pdf")):
            with self.assertRaises(ClientError) as ctx:
                self._call("http://example.com/doc.pdf", MagicMock())
        self.assertIn("url_not_accessible", str(ctx.exception))

    def test_download_uses_provided_session(self):
        """Tests that the PDF download goes through the session passed by async_invoke."""
        data = make_pdf_bytes()
        session, _ = make_stream_session([data])
        self._call("http://example.com/doc.pdf", session)
        session.get.assert_called_once()
        self.assertEqual(session.get.call_args.args[0], "http://example.com/doc.pdf")
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
