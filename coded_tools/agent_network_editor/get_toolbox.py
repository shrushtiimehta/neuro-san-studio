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

import logging
import os
from asyncio import to_thread
from threading import Lock
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool
from neuro_san.internals.run_context.langchain.toolbox.toolbox_info_restorer import ToolboxInfoRestorer

from coded_tools.agent_network_editor.and_logger import AndLogger

DEFAULT_TOOLBOX_INFO_FILE = os.path.join("neuro_san_studio", "toolbox", "agent_network_designer_toolbox_info.hocon")
logger = AndLogger(logging.getLogger(__name__))


class GetToolbox(CodedTool):
    """
    CodedTool implementation which provides a way to get tool definition from toolbox info file
    """

    # Process-wide cache of the {tool_name: description} mapping parsed from the
    # toolbox info file (issue #1268). The file path — the
    # AGENT_NETWORK_DESIGNER_TOOLBOX_INFO_FILE env var or the default — is
    # resolved at first use and the parse happens once per process; the cache is
    # deliberately never refreshed, so picking up an edited toolbox info file
    # requires a process restart. This is the same trade-off already made for
    # ConnectivityDictionaryConverter's shared ToolboxFactory. Previously the
    # cache lived in sly_data, so a server handling N concurrent conversations
    # re-parsed the same HOCON N times, on the event loop.
    _shared_toolbox_info: dict[str, str] | None = None

    # A threading.Lock rather than an asyncio.Lock: callers may run on
    # different event loops in different threads, and an asyncio.Lock cannot
    # be shared across event loops.
    _shared_toolbox_info_lock = Lock()

    @classmethod
    def peek_shared_toolbox_info(cls) -> dict[str, str] | None:
        """
        :return: The shared toolbox info if it has already been loaded, else None.
                Lock-free and safe to call from any thread or event loop. Async
                callers can use a None result to decide to run
                get_shared_toolbox_info() in a worker thread instead of on the
                event loop. Treat the result as read-only: it is the live
                shared cache, not a copy — mutating it corrupts every
                conversation in the process. get_toolbox_info() returns a
                mutation-safe copy.
        """
        return GetToolbox._shared_toolbox_info

    @classmethod
    def get_shared_toolbox_info(cls) -> dict[str, str]:
        """
        Get the process-wide toolbox info, reading and parsing the file on first call.

        The first call in the process does file I/O plus a HOCON parse, so
        async callers should check peek_shared_toolbox_info() first and reach
        this through asyncio.to_thread() on a miss. Once loaded, calls return
        via a lock-free read.

        Note: cache access goes through the class by name (not cls) so a
        hypothetical subclass shares the one cache instead of splitting it.
        All reads funnel through peek_shared_toolbox_info() so any future
        cache policy (expiration, refresh) has a single interception point;
        only the publishes below touch the attribute directly.

        :return: dict mapping tool names to descriptions; empty if the toolbox
                info file does not exist. Failures are never published: a
                missing file returns empty for this call only and the next
                call retries, so a transient gap (a deploy replacing the file,
                a not-yet-mounted volume) cannot pin an empty toolbox for the
                life of the process. A malformed file raises out of the parse,
                also unpublished. Treat the result as read-only: it is the
                live shared cache, not a copy — get_toolbox_info() returns a
                mutation-safe copy.
        """
        tools: dict[str, str] | None = GetToolbox.peek_shared_toolbox_info()
        if tools is not None:
            # Lock-free fast path: the attribute is published only after a
            # fully successful load-and-clean, and reference reads are atomic
            # under the GIL, so a non-None read always yields a complete dict.
            return tools

        with GetToolbox._shared_toolbox_info_lock:
            tools = GetToolbox.peek_shared_toolbox_info()
            if tools is not None:
                return tools

            # Check for toolbox info file in env var
            toolbox_info_file: str = os.getenv("AGENT_NETWORK_DESIGNER_TOOLBOX_INFO_FILE")
            if not toolbox_info_file:
                # Use a default if no value specified
                toolbox_info_file = DEFAULT_TOOLBOX_INFO_FILE

            # Go fish — once per process once it succeeds.
            logger.info(">>>>>>>>>>>>>>>>>>>Getting Tool Definition from Toolbox>>>>>>>>>>>>>>>>>>>")
            logger.info("Toolbox info file: %s", toolbox_info_file)

            try:
                raw_tools: dict[str, Any] = ToolboxInfoRestorer().restore(toolbox_info_file)
            except FileNotFoundError:
                # Return empty WITHOUT publishing: caching the failure would
                # serve an empty toolbox to every conversation until process
                # restart, even after an operator restores the file (deploy
                # races and wrong-CWD launches make a missing file a transient
                # condition). The retry costs one failed open per call, and
                # the recurring warning is the operator's signal.
                logger.warning("Error: Failed to load toolbox info from %s.", toolbox_info_file)
                return {}

            logger.info("Successfully loaded the following toolbox: %s", str(raw_tools))

            # Keep only each tool's description.
            tools = {}
            for tool_name, tool_info in raw_tools.items():
                tools[tool_name] = tool_info.get("description", "")

            # Publish only after the load-and-clean fully succeeded. Parse
            # errors propagate out of the restore above without publishing,
            # so a transiently broken file is retried on the next call
            # instead of poisoning the cache.
            GetToolbox._shared_toolbox_info = tools

        return tools

    @classmethod
    def clear_shared_toolbox_info_for_testing(cls):
        """
        Reset the process-wide toolbox info cache. For test isolation only.

        Production code must never call this: the cache is deliberately
        load-once-per-process (see the class comment above). Tests call it
        (via tests/conftest.py) so toolbox info loaded under one test's
        AGENT_NETWORK_DESIGNER_TOOLBOX_INFO_FILE state cannot leak into later
        tests. Living here rather than in conftest keeps all the singleton
        policy in this one class.
        """
        # Taking the lock serializes the reset with a concurrent first load,
        # so this can never unpublish a mapping mid-initialization.
        with GetToolbox._shared_toolbox_info_lock:
            GetToolbox._shared_toolbox_info = None

    @staticmethod
    async def get_toolbox_info() -> dict[str, str]:
        """
        Read toolbox info from the process-wide cache, loading it from a file
        on the first call in the process.

        :return: dict mapping tool names to descriptions; empty if the toolbox
                info file does not exist (retried on the next call, never
                cached). A malformed file raises. The returned dict is a copy,
                so callers may mutate it without corrupting the shared cache.
        """
        tools: dict[str, str] | None = GetToolbox.peek_shared_toolbox_info()
        if tools is None:
            # Cold path — once per process on success, once per call while
            # the file is missing: keep the file read and HOCON parse off
            # the event loop.
            tools = await to_thread(GetToolbox.get_shared_toolbox_info)
        return dict(tools)

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args: An argument dictionary whose keys are the parameters
                to the coded tool and whose values are the values passed for them
                by the calling agent.  This dictionary is to be treated as read-only.

                The argument dictionary expects the following keys:
                    None

        :param sly_data: A dictionary whose keys are defined by the agent hierarchy,
                but whose values are meant to be kept out of the chat stream.

                This dictionary is largely to be treated as read-only.
                It is possible to add key/value pairs to this dict that do not
                yet exist as a bulletin board, as long as the responsibility
                for which coded_tool publishes new entries is well understood
                by the agent chain implementation and the coded_tool implementation
                adding the data is not invoke()-ed more than once.

                Keys expected for this implementation are:
                    None

        :return:
            In case of successful execution:
                the tool definition from toolbox as a dictionary.
            otherwise:
                an empty dictionary if the toolbox info file does not exist;
                a malformed file raises.
        """
        return await self.get_toolbox_info()
