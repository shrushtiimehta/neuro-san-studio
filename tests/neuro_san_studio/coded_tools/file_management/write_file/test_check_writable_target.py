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

import tempfile
from pathlib import Path
from unittest import TestCase

from neuro_san_studio.coded_tools.file_management.write_file import WriteFile


class TestCheckWritableTarget(TestCase):
    """Unit tests for WriteFile._check_writable_target."""

    def setUp(self):
        self.tool = WriteFile()
        self.tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.tmp_root = Path(self.tmpdir.name).resolve()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _call(self, path: Path, overwrite: bool) -> None:
        """Invoke _check_writable_target; returns None or raises."""
        self.tool._check_writable_target(path, overwrite)  # pylint: disable=protected-access

    def test_new_path_passes(self):
        """Tests that a path that does not exist yet passes regardless of overwrite."""
        path = self.tmp_root / "new.txt"
        self._call(path, False)  # should not raise
        self._call(path, True)  # should not raise

    def test_existing_file_with_overwrite_passes(self):
        """Tests that an existing file passes when overwrite is True."""
        path = self.tmp_root / "existing.txt"
        path.write_text("x", encoding="utf-8")
        self._call(path, True)  # should not raise

    def test_existing_file_without_overwrite_raises(self):
        """Tests that an existing file raises file_already_exists when overwrite is False."""
        path = self.tmp_root / "existing.txt"
        path.write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self._call(path, False)
        self.assertIn("file_already_exists", str(ctx.exception))

    def test_directory_raises_even_with_overwrite(self):
        """Tests that a directory target raises is_a_directory even when overwrite is True."""
        path = self.tmp_root / "subdir"
        path.mkdir()
        for overwrite in (False, True):
            with self.assertRaises(ValueError) as ctx:
                self._call(path, overwrite)
            self.assertIn("is_a_directory", str(ctx.exception))
