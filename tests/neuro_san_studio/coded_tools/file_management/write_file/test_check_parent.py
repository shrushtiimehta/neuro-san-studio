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


class TestCheckParent(TestCase):
    """Unit tests for WriteFile._check_parent."""

    def setUp(self):
        self.tool = WriteFile()
        self.tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.tmp_root = Path(self.tmpdir.name).resolve()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _call(self, path: Path, create_parents: bool) -> None:
        """Invoke _check_parent; returns None or raises."""
        self.tool._check_parent(path, create_parents)  # pylint: disable=protected-access

    def test_existing_parent_passes(self):
        """Tests that a file whose parent directory exists passes regardless of create_parents."""
        path = self.tmp_root / "file.txt"
        self._call(path, False)  # should not raise
        self._call(path, True)  # should not raise

    def test_missing_parent_with_create_parents_passes(self):
        """Tests that a missing parent passes when create_parents is True."""
        path = self.tmp_root / "a" / "b" / "file.txt"
        self._call(path, True)  # should not raise

    def test_missing_parent_without_create_parents_raises(self):
        """Tests that a missing parent raises parent_not_found when create_parents is False."""
        path = self.tmp_root / "a" / "b" / "file.txt"
        with self.assertRaises(ValueError) as ctx:
            self._call(path, False)
        self.assertIn("parent_not_found", str(ctx.exception))

    def test_parent_is_a_file_raises_even_with_create_parents(self):
        """Tests that a parent path occupied by a regular file raises parent_not_a_directory regardless of flag."""
        blocker = self.tmp_root / "blocker"
        blocker.write_text("x", encoding="utf-8")
        path = blocker / "file.txt"
        for create_parents in (False, True):
            with self.assertRaises(ValueError) as ctx:
                self._call(path, create_parents)
            self.assertIn("parent_not_a_directory", str(ctx.exception))
