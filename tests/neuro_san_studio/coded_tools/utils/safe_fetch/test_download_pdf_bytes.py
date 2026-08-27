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
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientError
from aiohttp import ClientResponseError

from neuro_san_studio.coded_tools.utils.safe_fetch import MAX_RESPONSE_BYTES
from neuro_san_studio.coded_tools.utils.safe_fetch import SafeFetch
from tests.neuro_san_studio.coded_tools.utils.safe_fetch.helpers import make_response_error
from tests.neuro_san_studio.coded_tools.utils.safe_fetch.helpers import make_stream_session


class TestDownloadPdfBytes(TestCase):
    """Unit tests for SafeFetch.download_pdf_bytes."""

    def _call(self, session, url: str = "http://example.com/doc.pdf") -> bytes:
        """Invoke download_pdf_bytes with the given mocked session."""
        return asyncio.run(SafeFetch.download_pdf_bytes(url, session))

    def test_joins_streamed_chunks(self):
        """Tests that streamed chunks are concatenated into the full body."""
        session, _ = make_stream_session([b"%PDF", b"-1.4", b" body"])
        self.assertEqual(self._call(session), b"%PDF-1.4 body")

    def test_redirect_raises_url_not_allowed(self):
        """Tests that a 3xx response raises ValueError with url_not_allowed."""
        session, _ = make_stream_session([], status=302)
        with self.assertRaises(ValueError) as ctx:
            self._call(session)
        self.assertIn("url_not_allowed", str(ctx.exception))

    def test_429_maps_to_too_many_requests(self):
        """Tests that HTTP 429 raises ClientResponseError with too_many_requests prefix."""
        session, _ = make_stream_session([], status=429, raise_for_status_exc=make_response_error(429))
        with self.assertRaises(ClientResponseError) as ctx:
            self._call(session)
        self.assertIn("too_many_requests", str(ctx.exception))

    def test_http_error_maps_to_url_not_accessible(self):
        """Tests that a non-2xx response raises ClientResponseError with url_not_accessible prefix."""
        session, _ = make_stream_session([], status=500, raise_for_status_exc=make_response_error(500))
        with self.assertRaises(ClientResponseError) as ctx:
            self._call(session)
        self.assertIn("url_not_accessible", str(ctx.exception))

    def test_content_length_header_over_limit_raises(self):
        """Tests that a Content-Length header above MAX_RESPONSE_BYTES raises response_too_large."""
        session, _ = make_stream_session([b"x"], content_length=MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(ValueError) as ctx:
            self._call(session)
        self.assertIn("response_too_large", str(ctx.exception))

    def test_streamed_body_over_limit_raises(self):
        """Tests that a body exceeding MAX_RESPONSE_BYTES on the wire raises response_too_large.

        This covers the server-lies-about-Content-Length case: the header is absent,
        so only the running byte count can enforce the cap.
        """
        session, _ = make_stream_session([b"x" * 8, b"y" * 8])
        with patch("neuro_san_studio.coded_tools.utils.safe_fetch.MAX_RESPONSE_BYTES", 10):
            with self.assertRaises(ValueError) as ctx:
                self._call(session)
        self.assertIn("response_too_large", str(ctx.exception))

    def test_connection_error_wrapped_as_url_not_accessible(self):
        """Tests that a connection-level ClientError is wrapped with url_not_accessible prefix."""
        session = MagicMock()
        session.get = MagicMock(side_effect=ClientError("connection reset"))
        with self.assertRaises(ClientError) as ctx:
            self._call(session)
        self.assertIn("url_not_accessible", str(ctx.exception))
