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
import sys

import pytest


@pytest.fixture(autouse=True)
def reset_shared_toolbox_factory():
    """
    Clear ConnectivityDictionaryConverter's process-wide ToolboxFactory cache
    after each test.

    The cache captures AGENT_TOOLBOX_INFO_FILE at its first load and is never
    refreshed, so without this reset a test that triggers a connectivity-style
    progress report would leak its loaded factory (and the env-var state it was
    built from) into every later test in the same process, producing
    order-dependent results.

    The module is looked up via sys.modules instead of imported directly so
    tests that never touch the converter don't pay for importing neuro-san
    internals at collection time.
    """
    yield
    module = sys.modules.get("coded_tools.agent_network_editor.connectivity_dictionary_converter")
    if module is not None:
        # pylint: disable=protected-access
        module.ConnectivityDictionaryConverter._shared_toolbox_factory = None
