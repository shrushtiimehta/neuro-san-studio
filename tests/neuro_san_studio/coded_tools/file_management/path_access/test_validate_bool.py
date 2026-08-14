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

from neuro_san_studio.coded_tools.file_management.path_access import PathAccess


class TestValidateBool(TestCase):
    """Unit tests for PathAccess.validate_bool."""

    def _call(self, args, param_name="test_flag", default=False):
        """Invoke validate_bool with the given args dict and return the result."""
        return PathAccess.validate_bool(args, param_name, default)

    def test_explicit_true_returned(self):
        """Tests that an explicit True value is returned."""
        self.assertTrue(self._call({"test_flag": True}))

    def test_explicit_false_returned(self):
        """Tests that an explicit False value is returned even when the default is True."""
        self.assertFalse(self._call({"test_flag": False}, default=True))

    def test_missing_returns_default(self):
        """Tests that an omitted parameter returns the provided default."""
        self.assertFalse(self._call({}))
        self.assertTrue(self._call({}, default=True))

    def test_non_bool_raises_invalid_input(self):
        """Tests that non-boolean values raise invalid_input (including truthy strings and ints)."""
        for bad in ["true", "yes", 1, 0, [], {}]:
            with self.assertRaises(ValueError) as ctx:
                self._call({"test_flag": bad})
            self.assertIn("invalid_input", str(ctx.exception))
