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
# Note on the filename: conftest.py is the exact name pytest requires for
# fixtures that apply automatically to every test under this directory —
# pytest discovers and loads it by name, so it cannot be renamed to something
# more descriptive without the autouse fixture below silently ceasing to run.
import sys

import pytest

# Central inventory of the process-wide caches used by the Agent Network
# Designer family, as (module, class, test-only clear method) triples. Each
# cache lives on its owning class as a peek / get / clear-for-testing triple
# (see ConnectivityDictionaryConverter.get_shared_toolbox_factory() for the
# canonical pattern). Each captures file/env-var state at its first load and
# is never refreshed, so a test that populates one would otherwise leak that
# state into every later test in the same process, producing order-dependent
# results. Add an entry here whenever a new shared cache is introduced.
_PROCESS_CACHE_CLEARERS: list[tuple[str, str, str]] = [
    # The loaded ToolboxFactory used for connectivity-style conversion
    # of agent network definitions (issue #1262).
    (
        "coded_tools.agent_network_editor.connectivity_dictionary_converter",
        "ConnectivityDictionaryConverter",
        "clear_shared_toolbox_factory_for_testing",
    ),
    # The {tool_name: description} mapping parsed from the designer's
    # toolbox info file (issue #1268).
    (
        "coded_tools.agent_network_editor.get_toolbox",
        "GetToolbox",
        "clear_shared_toolbox_info_for_testing",
    ),
]


def _clear_process_caches():
    """
    Clear every registered process-wide cache.

    Modules are looked up via sys.modules instead of imported directly so
    tests that never touch these classes don't pay for importing neuro-san
    internals at collection time.
    """
    for module_name, class_name, clear_method_name in _PROCESS_CACHE_CLEARERS:
        module = sys.modules.get(module_name)
        if module is not None:
            getattr(getattr(module, class_name), clear_method_name)()


@pytest.fixture(autouse=True)
def reset_process_caches():
    """
    Clear the process-wide caches before and after each test.

    Clearing before the test as well guards against state populated outside
    any test, e.g. during collection or session setup.
    """
    _clear_process_caches()
    yield
    _clear_process_caches()
