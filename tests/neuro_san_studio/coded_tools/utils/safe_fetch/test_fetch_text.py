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
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientError
from aiohttp import ClientResponseError

from neuro_san_studio.coded_tools.utils.safe_fetch import SafeFetch
from tests.neuro_san_studio.coded_tools.utils.safe_fetch.helpers import make_get_response
from tests.neuro_san_studio.coded_tools.utils.safe_fetch.helpers import make_response_error

MODULE = "neuro_san_studio.coded_tools.utils.safe_fetch"


class TestFetchText(TestCase):
    """Unit tests for SafeFetch.fetch_text."""

    def test_plain_text_returned_as_is(self):
        """Tests that plain text body content is returned unchanged."""
        session, _ = make_get_response(body="just plain text")
        result = asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertEqual(result, "just plain text")

    def test_html_is_stripped(self):
        """Tests that HTML tags, scripts, and styles are stripped from the fetched content."""
        html = "<html><head><style>body{}</style></head><body><p>Hello</p><script>alert(1)</script></body></html>"
        session, _ = make_get_response(body=html)
        result = asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertIn("Hello", result)
        self.assertNotIn("<p>", result)
        self.assertNotIn("alert", result)
        self.assertNotIn("body{}", result)

    def test_non_2xx_raises_client_response_error_with_prefix(self):
        """Tests that a non-2xx HTTP error raises ClientResponseError with url_not_accessible prefix."""
        exc = make_response_error(503)
        session, _ = make_get_response(status=503, raise_for_status_exc=exc)
        with self.assertRaises(ClientResponseError) as ctx:
            asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertIn("url_not_accessible", ctx.exception.message)

    def test_429_raises_with_too_many_requests_prefix(self):
        """Tests that a 429 response raises ClientResponseError with too_many_requests prefix."""
        exc = make_response_error(429)
        session, _ = make_get_response(status=429, raise_for_status_exc=exc)
        with self.assertRaises(ClientResponseError) as ctx:
            asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertIn("too_many_requests", ctx.exception.message)

    def test_redirect_raises_url_not_allowed(self):
        """Tests that a 3xx GET response raises ValueError with url_not_allowed and the Location URL."""
        session, response = make_get_response(status=301)
        response.headers["Location"] = "http://other.com/"

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        error = str(ctx.exception)
        self.assertIn("url_not_allowed", error)
        self.assertIn("http://other.com/", error)

    def test_connection_error_raises_client_error_with_prefix(self):
        """Tests that a connection error raises ClientError with url_not_accessible prefix."""
        response_cm = MagicMock()
        response_cm.__aenter__ = AsyncMock(side_effect=ClientError("connection reset"))
        response_cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=response_cm)

        with self.assertRaises(ClientError) as ctx:
            asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertIn("url_not_accessible", str(ctx.exception))

    def test_body_over_limit_raises_response_too_large(self):
        """Tests that a text body exceeding MAX_RESPONSE_BYTES raises response_too_large.

        Guards the text path's own streamed size cap, independent of the HEAD probe
        in get_content_type — the gap a direct fetch_text caller would otherwise hit.
        """
        session, _ = make_get_response(body="x" * 50)
        with patch(f"{MODULE}.MAX_RESPONSE_BYTES", 10):
            with self.assertRaises(ValueError) as ctx:
                asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertIn("response_too_large", str(ctx.exception))

    def test_private_ip_url_rejected_without_network(self):
        """Tests that fetch_text validates the URL itself, blocking SSRF even without a prior validate_url call.

        The session's get is a MagicMock that would 'succeed' if reached; the raised
        url_not_allowed confirms validation happens at the fetch boundary.
        """
        session = MagicMock()
        session.get = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(SafeFetch.fetch_text("http://169.254.169.254/latest/meta-data/", session))
        self.assertIn("url_not_allowed", str(ctx.exception))
        session.get.assert_not_called()

    def test_invalid_charset_falls_back_to_utf8(self):
        """Tests that a malformed Content-Type charset never escapes as an untranslated LookupError.

        A server may declare a codec Python does not know; bytes.decode() then raises
        LookupError at codec lookup, before errors="replace" can apply. That error is
        neither ClientError nor a timeout, so it would bypass the fetch methods'
        translation and break their url_not_accessible contract. The decode must fall
        back to utf-8 and return the body instead of raising.
        """
        response = MagicMock()
        response.status = 200
        response.headers = {"Content-Type": "text/plain; charset=not-a-real-codec"}
        response.charset = "not-a-real-codec"
        response.raise_for_status = MagicMock()

        async def iter_chunked(_chunk_size):
            # Valid utf-8 bytes; only the declared charset token is bogus.
            yield "héllo".encode("utf-8")

        response.content.iter_chunked = iter_chunked
        response_cm = MagicMock()
        response_cm.__aenter__ = AsyncMock(return_value=response)
        response_cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=response_cm)

        result = asyncio.run(SafeFetch.fetch_text("http://example.com", session))
        self.assertEqual(result, "héllo")
