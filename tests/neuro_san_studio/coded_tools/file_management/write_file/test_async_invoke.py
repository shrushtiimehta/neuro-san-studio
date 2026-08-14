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
import tempfile
from pathlib import Path
from unittest import TestCase

from neuro_san_studio.coded_tools.file_management.write_file import WRITE_FILE_HISTORY_KEY
from neuro_san_studio.coded_tools.file_management.write_file import WriteFile


class TestAsyncInvoke(TestCase):
    """Integration-level tests for WriteFile.async_invoke using a real temp directory."""

    def setUp(self):
        self.tool = WriteFile()
        self.sly_data: dict = {}
        self.tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.tmp_root = Path(self.tmpdir.name).resolve()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _invoke(self, args: dict) -> dict:
        """Invoke the tool with allowed_paths defaulted to the temp root."""
        args.setdefault("allowed_paths", [str(self.tmp_root)])
        return asyncio.run(self.tool.async_invoke(args, self.sly_data))

    def test_writes_new_file_within_allowed_path(self):
        """Tests that a new file is written and the result carries the expected keys."""
        path = self.tmp_root / "out.txt"
        result = self._invoke({"file_path": str(path), "content": "hello"})
        self.assertEqual(path.read_text(encoding="utf-8"), "hello")
        self.assertEqual(result["path"], str(path))
        self.assertEqual(result["bytes_written"], 5)
        self.assertTrue(result["created"])
        self.assertIn("written_at", result)

    def test_overwrite_requires_opt_in(self):
        """Tests that writing over an existing file fails by default and works with overwrite=True."""
        path = self.tmp_root / "out.txt"
        path.write_text("old", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "new"})
        self.assertIn("file_already_exists", str(ctx.exception))
        self.assertEqual(path.read_text(encoding="utf-8"), "old")

        result = self._invoke({"file_path": str(path), "content": "new", "overwrite": True})
        self.assertEqual(path.read_text(encoding="utf-8"), "new")
        self.assertFalse(result["created"])

    def test_create_parents_requires_opt_in(self):
        """Tests that a missing parent fails by default and works with create_parents=True."""
        path = self.tmp_root / "a" / "b" / "out.txt"
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "x"})
        self.assertIn("parent_not_found", str(ctx.exception))

        self._invoke({"file_path": str(path), "content": "x", "create_parents": True})
        self.assertEqual(path.read_text(encoding="utf-8"), "x")

    def test_omitted_allowed_paths_raises_invalid_input(self):
        """Tests that omitting the required allowed_paths raises invalid_input."""
        path = self.tmp_root / "out.txt"
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(self.tool.async_invoke({"file_path": str(path), "content": "x"}, self.sly_data))
        self.assertIn("invalid_input", str(ctx.exception))
        self.assertFalse(path.exists())

    def test_path_outside_allowed_root_denied(self):
        """Tests that a path outside any allowed_paths entry is denied before touching disk."""
        path = self.tmp_root / "out.txt"
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "x", "allowed_paths": ["/some/other/root"]})
        self.assertIn("path_not_allowed", str(ctx.exception))
        self.assertFalse(path.exists())

    def test_access_denied_takes_priority_over_existing_file(self):
        """Tests that out-of-scope paths surface path_not_allowed, never file_already_exists."""
        path = self.tmp_root / "out.txt"
        path.write_text("secret", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "x", "allowed_paths": ["/some/other/root"]})
        self.assertIn("path_not_allowed", str(ctx.exception))

    def test_extension_not_in_allowlist_denied(self):
        """Tests that an extension outside allowed_file_extensions is denied."""
        path = self.tmp_root / "out.exe"
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "x", "allowed_file_extensions": [".txt"]})
        self.assertIn("path_not_allowed", str(ctx.exception))

    def test_blocked_extension_denied(self):
        """Tests that a blocked extension is denied even inside an allowed path."""
        path = self.tmp_root / ".env"
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "x", "blocked_file_extensions": [".env"]})
        self.assertIn("path_not_allowed", str(ctx.exception))

    def test_directory_target_raises(self):
        """Tests that writing to an existing directory raises is_a_directory."""
        subdir = self.tmp_root / "subdir"
        subdir.mkdir()
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(subdir), "content": "x", "overwrite": True})
        self.assertIn("is_a_directory", str(ctx.exception))

    def test_non_bool_overwrite_raises_invalid_input(self):
        """Tests that a non-boolean overwrite value raises invalid_input."""
        path = self.tmp_root / "out.txt"
        with self.assertRaises(ValueError) as ctx:
            self._invoke({"file_path": str(path), "content": "x", "overwrite": "yes"})
        self.assertIn("invalid_input", str(ctx.exception))

    def test_write_history_recorded_and_deduped(self):
        """Tests that written paths land in sly_data write history, deduped and insertion-ordered."""
        path_a = self.tmp_root / "a.txt"
        path_b = self.tmp_root / "b.txt"
        self._invoke({"file_path": str(path_a), "content": "1"})
        self._invoke({"file_path": str(path_b), "content": "2"})
        self._invoke({"file_path": str(path_a), "content": "3", "overwrite": True})
        self.assertEqual(self.sly_data[WRITE_FILE_HISTORY_KEY], [str(path_a), str(path_b)])

    def test_relative_path_resolved_within_allowed_root(self):
        """Tests that the reported path is the resolved absolute path."""
        path = self.tmp_root / "sub" / ".." / "rel.txt"
        result = self._invoke({"file_path": str(path), "content": "x"})
        self.assertEqual(result["path"], str(self.tmp_root / "rel.txt"))
        self.assertTrue((self.tmp_root / "rel.txt").exists())
