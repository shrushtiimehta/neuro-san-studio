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
import logging
import os
from pathlib import Path
from time import monotonic
from typing import Any

from langchain_core.tools import BaseTool
from neuro_san.interfaces.coded_tool import CodedTool
from neuro_san.internals.run_context.langchain.mcp.langchain_mcp_adapter import LangChainMcpAdapter
from neuro_san.internals.run_context.langchain.mcp.mcp_servers_info_restorer import McpServersInfoRestorer

from coded_tools.agent_network_editor.and_logger import AndLogger
from coded_tools.agent_network_editor.shared_process_cache import SharedProcessCache
from neuro_san_studio import mcp as _mcp_pkg

# Path to the mcp_info.hocon shipped inside the neuro_san_studio package.
# Resolved via the imported package's __file__ so it works both in-repo and
# after `pip install` on every platform. Mirrors run.py.
BUNDLED_MCP_INFO_FILE: Path = Path(_mcp_pkg.__file__).parent / "mcp_info.hocon"

# Cap on how long one MCP server may take to answer a tool listing. The
# listings are fetched by a process-wide shared load, so without a cap a
# single hung server would stall every conversation's get_mcp_tool call
# (previously it only stalled the one conversation doing the fetch). A slow
# server is logged, omitted from this round's result, and retried after the
# TTL window.
MCP_TOOLS_FETCH_TIMEOUT_SECONDS: float = 30.0

logger = AndLogger(logging.getLogger(__name__))


class GetMcpTool(CodedTool):
    """
    CodedTool implementation which provides a way to get tool definition from given MCP servers
    """

    # TODO: This duplicates NeuroSanRunner._resolve_mcp_info_file in
    # neuro_san_studio/commands/run.py. Refactor so run.py calls this method
    # instead of maintaining its own copy.
    @staticmethod
    def get_mcp_info_file() -> str:
        """Resolve the mcp_info.hocon path at call time.

        Precedence (mirrors NeuroSanRunner._resolve_mcp_info_file):
          1. MCP_SERVERS_INFO_FILE env var (used verbatim if non-empty).
          2. <cwd>/mcp/mcp_info.hocon if it exists (what `init` scaffolds).
          3. The mcp_info.hocon bundled in the neuro_san_studio package.
        """
        env_value = os.getenv("MCP_SERVERS_INFO_FILE")
        if env_value:
            return env_value
        scaffolded = Path.cwd() / "mcp" / "mcp_info.hocon"
        if scaffolded.is_file():
            return str(scaffolded)
        return str(BUNDLED_MCP_INFO_FILE)

    @staticmethod
    def _mcp_info_fingerprint() -> tuple[str, int | None]:
        """
        Freshness probe for the shared MCP-servers cache (see
        SharedProcessCache): the cached list is served only while this value
        is unchanged. Unlike the designer manifest there is no time bucket:
        mcp_info.hocon is a plain config file with no `include`s and nothing
        writes it at runtime, so the two components cover everything —

        * the resolved path — an env-var change or the cwd-scaffolded file
          appearing takes effect on the next read;
        * the file's mtime — a direct edit invalidates immediately, and a
          missing file (mtime None) self-heals the moment it appears.

        :return: (path, mtime_ns or None) tuple.
        """
        mcp_info_file: str = GetMcpTool.get_mcp_info_file()
        try:
            mtime_ns: int | None = os.stat(mcp_info_file).st_mtime_ns
        except OSError:
            mtime_ns = None
        return (mcp_info_file, mtime_ns)

    @staticmethod
    def _load_mcp_servers() -> list[str]:
        """
        Loader for the shared MCP-servers list (runs inside
        SharedProcessCache, off the event loop when reached via aget()).

        :return: List of MCP server URLs from mcp_info.hocon. A missing or
                unparseable file returns an empty list, which IS published:
                the fingerprint self-heals it — a missing file flips the
                mtime component when it appears, and fixing a broken file
                changes its mtime — so nothing can pin an empty list past
                the next change to the file itself.
        """
        mcp_info_file: str = GetMcpTool.get_mcp_info_file()
        logger.info("MCP servers info file: %s", mcp_info_file)

        servers: list[str] = []
        try:
            # McpServersInfoRestorer is constructed with must_exist=False, so
            # a missing file comes back as None rather than an exception.
            info: dict[str, Any] = McpServersInfoRestorer().restore(file_reference=mcp_info_file)
            if info is None:
                logger.warning("MCP servers info file not found at %s. No MCP Servers will be used.", mcp_info_file)
                info = {}
            servers = list(info.keys())
        except ValueError as error:
            # neuro-san re-wraps HOCON parse errors as ValueError.
            logger.warning("Failed to parse MCP servers info file %s: %s", mcp_info_file, error)
        return servers

    # Process-wide cache of the MCP server URLs parsed from mcp_info.hocon.
    # Previously cached per sly_data scope, so a server handling N concurrent
    # conversations re-parsed the same HOCON N times, on the event loop.
    # The (path, mtime) fingerprint picks up env-var changes and file edits
    # immediately; there is no time bucket because nothing changes this file
    # at runtime. Locking, publish ordering, and the async once-gate live in
    # SharedProcessCache; access goes through the class by name (not cls) so
    # a hypothetical subclass shares the one cache instead of splitting it.
    _shared_mcp_servers_cache: SharedProcessCache[list[str]] = SharedProcessCache(
        loader=_load_mcp_servers, fingerprint=_mcp_info_fingerprint
    )

    @staticmethod
    def _mcp_tools_ttl_seconds() -> float:
        """
        :return: How long the shared tool-descriptions mapping may be served
                before the listings are re-fetched from the MCP servers, from
                the AGENT_NETWORK_DESIGNER_MCP_TOOLS_TTL_SECONDS env var
                (default 300). Unlike the file-backed caches there is no
                local change to observe — the servers are external and their
                tool sets can change (or an outage can end) without any local
                signal — so a TTL is the freshness mechanism, and it doubles
                as the recovery bound after a failed or partial fetch.
                <= 0 disables time-based refresh entirely: the listings are
                fetched once and only an mcp_info.hocon change refreshes
                them. An unparseable value falls back to the default.
        """
        try:
            return float(os.getenv("AGENT_NETWORK_DESIGNER_MCP_TOOLS_TTL_SECONDS", "300"))
        except ValueError:
            return 300.0

    @staticmethod
    def _mcp_tools_fingerprint() -> tuple[str, int | None, int]:
        """
        Freshness probe for the shared tool-descriptions cache: the
        MCP-servers-list fingerprint (so an mcp_info.hocon edit refreshes the
        listings immediately) plus a time bucket that rolls once per TTL
        window (see _mcp_tools_ttl_seconds; frozen when TTL <= 0).

        :return: (path, mtime_ns or None, time bucket) tuple.
        """
        mcp_info_file, mtime_ns = GetMcpTool._mcp_info_fingerprint()
        ttl: float = GetMcpTool._mcp_tools_ttl_seconds()
        time_bucket: int = int(monotonic() / ttl) if ttl > 0 else 0
        return (mcp_info_file, mtime_ns, time_bucket)

    @staticmethod
    def _load_mcp_tool_descriptions() -> dict[str, str]:
        """
        Loader for the shared tool-descriptions mapping (runs inside
        SharedProcessCache, in a worker thread when reached via aget()).

        Fetches every configured server's tool listing CONCURRENTLY on a
        private event loop (asyncio.run — legal here because the loader runs
        in a worker thread, never on the server's loop). The old per-session
        code fetched sequentially, paying the sum of the servers' latencies
        per conversation; gather pays only the slowest.

        :return: dict mapping each server URL to a newline-joined string of
                its tools' descriptions. Servers that fail or time out are
                logged and omitted (matching the old per-session behavior),
                and the result — possibly empty — IS published: the entry
                self-expires via the TTL bucket, so an outage cannot poison
                the process beyond one window, and publishing prevents a
                per-call fetch storm during it.
        """
        # Already in a worker thread here, so the blocking get() is fine.
        servers: list[str] = GetMcpTool._shared_mcp_servers_cache.get()

        async def fetch_one(server: str) -> tuple[str, str | None]:
            logger.info("MCP Server: %s", server)
            try:
                tools: list[BaseTool] = await asyncio.wait_for(
                    LangChainMcpAdapter().get_mcp_tools(server), timeout=MCP_TOOLS_FETCH_TIMEOUT_SECONDS
                )
            except Exception as error:  # pylint: disable=broad-exception-caught
                # Broad on purpose: this is a shared load, so one bad server
                # (ExceptionGroup out of the MCP client, TimeoutError from
                # the cap above, connection errors, ...) must not take out
                # every conversation's listing of the healthy servers.
                logger.warning("Error: Failed to load tools from %s. %s", server, error)
                return server, None
            logger.info("Successfully loaded the following tools: %s", str(tools))

            # Gather each tool's description into one string.
            description: str = ""
            for tool in tools:
                description += tool.description + "\n"
            return server, description

        async def fetch_all() -> dict[str, str]:
            results = await asyncio.gather(*[fetch_one(server) for server in servers])
            return {server: description for server, description in results if description is not None}

        return asyncio.run(fetch_all())

    # Process-wide cache of the {server URL: tool descriptions} mapping
    # fetched from the MCP servers themselves. Previously cached per sly_data
    # scope, so every conversation paid the full network round-trip to every
    # server (sequentially). The sources are external servers with no local
    # change signal, so freshness is time-based: the fingerprint reuses the
    # mcp_info.hocon (path, mtime) probe — a config edit refreshes
    # immediately — plus a TTL bucket (default 300s, see
    # _mcp_tools_ttl_seconds) that bounds both staleness and how long a
    # failed fetch's empty/partial result can be served. Locking, publish
    # ordering, and the async once-gate live in SharedProcessCache; access
    # goes through the class by name (not cls) so a hypothetical subclass
    # shares the one cache instead of splitting it.
    _shared_mcp_tool_descriptions_cache: SharedProcessCache[dict[str, str]] = SharedProcessCache(
        loader=_load_mcp_tool_descriptions, fingerprint=_mcp_tools_fingerprint
    )

    @classmethod
    def clear_shared_mcp_servers_for_testing(cls):
        """
        Reset the process-wide MCP-servers cache. For test isolation only.

        Production code must never call this — staleness is already bounded
        by the fingerprint. Tests call it (via tests/conftest.py) so a list
        loaded under one test's MCP_SERVERS_INFO_FILE state cannot leak into
        later tests. Living here rather than in conftest keeps all the
        singleton policy in this one class.
        """
        GetMcpTool._shared_mcp_servers_cache.clear_for_testing()

    @classmethod
    def clear_shared_mcp_tool_descriptions_for_testing(cls):
        """
        Reset the process-wide tool-descriptions cache. For test isolation
        only — see clear_shared_mcp_servers_for_testing.
        """
        GetMcpTool._shared_mcp_tool_descriptions_cache.clear_for_testing()

    @staticmethod
    async def get_mcp_servers() -> list[str]:
        """
        Get the list of MCP server URLs from mcp_info.hocon.

        Used by callers (e.g. middleware) that need to validate MCP
        references. Reads only the config file, not the servers — and at
        most once per process per config change, off the event loop, shared
        by concurrent cold callers.

        :return: List of MCP server URLs, or an empty list if the file is
                missing or fails to parse (see the loader for the
                self-healing semantics). The returned list is a copy, so
                callers may mutate it without corrupting the shared cache.
        """
        return list(await GetMcpTool._shared_mcp_servers_cache.aget())

    @staticmethod
    async def get_mcp_tool_descriptions() -> dict[str, str]:
        """
        Get the {server URL: tool descriptions} mapping, fetching from the
        MCP servers at most once per process per TTL window (or config
        change), off the event loop, shared by concurrent cold callers.

        :return: dict mapping each server URL to a newline-joined string of
                its tools' descriptions; servers that failed this round are
                absent (retried after the TTL window). The returned dict is
                a copy, so callers may mutate it without corrupting the
                shared cache.
        """
        return dict(await GetMcpTool._shared_mcp_tool_descriptions_cache.aget())

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
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
                the server name and tool definition from the server as a dictionary.
            otherwise:
                servers that failed to respond are omitted; an empty
                dictionary if none responded or none are configured.
        """

        # Get tool list from MCP servers
        logger.info(">>>>>>>>>>>>>>>>>>>Getting Tool Definition from MCP Servers>>>>>>>>>>>>>>>>>>>")

        return str(await self.get_mcp_tool_descriptions())
