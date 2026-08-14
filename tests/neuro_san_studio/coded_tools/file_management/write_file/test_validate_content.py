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

from unittest import TestCase

from neuro_san_studio.coded_tools.file_management.write_file import MAX_WRITE_BYTES
from neuro_san_studio.coded_tools.file_management.write_file import WriteFile


class TestValidateContent(TestCase):
    """Unit tests for WriteFile._validate_content."""

    def setUp(self):
        self.tool = WriteFile()

    def _call(self, args):
        """Invoke _validate_content with the given args dict and return the encoded bytes."""
        return self.tool._validate_content(args)  # pylint: disable=protected-access

    def test_plain_string_encoded(self):
        """Tests that a plain string is returned UTF-8 encoded."""
        result = self._call({"content": "hello"})
        self.assertEqual(result, b"hello")

    def test_empty_string_allowed(self):
        """Tests that an empty string is valid content (creates an empty file)."""
        result = self._call({"content": ""})
        self.assertEqual(result, b"")

    def test_multibyte_characters_encoded(self):
        """Tests that multi-byte characters are measured in encoded bytes, not characters."""
        result = self._call({"content": "héllo"})
        self.assertEqual(result, "héllo".encode("utf-8"))
        self.assertEqual(len(result), 6)

    def test_missing_content_raises(self):
        """Tests that a missing 'content' key raises invalid_input."""
        with self.assertRaises(ValueError) as ctx:
            self._call({})
        self.assertIn("invalid_input", str(ctx.exception))

    def test_non_string_content_raises(self):
        """Tests that non-string content raises invalid_input."""
        for bad in [123, b"bytes", ["list"], {"dict": 1}, None]:
            with self.assertRaises(ValueError) as ctx:
                self._call({"content": bad})
            self.assertIn("invalid_input", str(ctx.exception))

    def test_content_at_limit_passes(self):
        """Tests that content exactly at the byte limit is allowed (boundary)."""
        result = self._call({"content": "x" * MAX_WRITE_BYTES})
        self.assertEqual(len(result), MAX_WRITE_BYTES)

    def test_content_over_limit_raises(self):
        """Tests that content one byte over the limit raises content_too_large."""
        with self.assertRaises(ValueError) as ctx:
            self._call({"content": "x" * (MAX_WRITE_BYTES + 1)})
        self.assertIn("content_too_large", str(ctx.exception))

    def test_multibyte_content_over_limit_raises(self):
        """Tests that the limit is enforced on encoded bytes so multi-byte chars can't sneak past."""
        # é is 2 bytes in UTF-8, so this is over the byte limit while under the char limit.
        with self.assertRaises(ValueError) as ctx:
            self._call({"content": "é" * ((MAX_WRITE_BYTES // 2) + 1)})
        self.assertIn("content_too_large", str(ctx.exception))
