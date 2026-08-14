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

import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from neuro_san_studio.coded_tools.file_management.write_file import WriteFile


class TestWriteAtomically(TestCase):
    """Unit tests for WriteFile._write_atomically."""

    def setUp(self):
        self.tool = WriteFile()
        self.tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.tmp_root = Path(self.tmpdir.name).resolve()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _call(self, path: Path, content: bytes, create_parents: bool = False) -> bool:
        """Invoke _write_atomically and return the 'created' flag."""
        return self.tool._write_atomically(path, content, create_parents)  # pylint: disable=protected-access

    def test_creates_new_file(self):
        """Tests that a new file is created with the expected content and created=True."""
        path = self.tmp_root / "new.txt"
        created = self._call(path, b"hello")
        self.assertTrue(created)
        self.assertEqual(path.read_bytes(), b"hello")

    def test_overwrites_existing_file(self):
        """Tests that an existing file is replaced and created=False is reported."""
        path = self.tmp_root / "existing.txt"
        path.write_text("old content", encoding="utf-8")
        created = self._call(path, b"new")
        self.assertFalse(created)
        self.assertEqual(path.read_bytes(), b"new")

    def test_writes_empty_content(self):
        """Tests that empty content produces an empty file."""
        path = self.tmp_root / "empty.txt"
        created = self._call(path, b"")
        self.assertTrue(created)
        self.assertEqual(path.read_bytes(), b"")

    def test_creates_missing_parents_when_asked(self):
        """Tests that missing parent directories are created when create_parents=True."""
        path = self.tmp_root / "a" / "b" / "deep.txt"
        created = self._call(path, b"x", create_parents=True)
        self.assertTrue(created)
        self.assertEqual(path.read_bytes(), b"x")

    def test_no_temp_file_left_behind_on_success(self):
        """Tests that the temp file used for atomicity is gone after a successful write."""
        path = self.tmp_root / "clean.txt"
        self._call(path, b"x")
        leftovers = [p.name for p in self.tmp_root.iterdir() if p.name != "clean.txt"]
        self.assertEqual(leftovers, [])

    def test_failed_replace_raises_write_error_and_cleans_up(self):
        """Tests that a failure during os.replace surfaces as write_error and leaves no temp file."""
        path = self.tmp_root / "fail.txt"
        with patch("neuro_san_studio.coded_tools.file_management.write_file.os.replace") as mock_replace:
            mock_replace.side_effect = OSError("disk full")
            with self.assertRaises(ValueError) as ctx:
                self._call(path, b"x")
        self.assertIn("write_error", str(ctx.exception))
        self.assertFalse(path.exists())
        self.assertEqual(list(self.tmp_root.iterdir()), [])

    def test_permission_error_raises_write_error(self):
        """Tests that a read-only target directory surfaces as write_error."""
        locked_dir = self.tmp_root / "locked"
        locked_dir.mkdir()
        os.chmod(locked_dir, 0o500)  # r-x only: temp file creation must fail
        try:
            path = locked_dir / "file.txt"
            with self.assertRaises(ValueError) as ctx:
                self._call(path, b"x")
            self.assertIn("write_error", str(ctx.exception))
        finally:
            os.chmod(locked_dir, 0o700)

    def test_mkdir_failure_raises_write_error(self):
        """Tests that a parent-creation failure surfaces as write_error."""
        locked_dir = self.tmp_root / "locked"
        locked_dir.mkdir()
        os.chmod(locked_dir, 0o500)  # r-x only: mkdir inside must fail
        try:
            path = locked_dir / "a" / "file.txt"
            with self.assertRaises(ValueError) as ctx:
                self._call(path, b"x", create_parents=True)
            self.assertIn("write_error", str(ctx.exception))
        finally:
            os.chmod(locked_dir, 0o700)
