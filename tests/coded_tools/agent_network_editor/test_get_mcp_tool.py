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
"""
Policy tests for GetMcpTool's process-wide caches: how the TTL and
per-server fetch cap are validated, what gets published, what must never be
published, and how failures degrade. The generic cache mechanism itself is
covered by test_shared_process_cache.py; these tests pin the policy layered
on top of it, with the MCP client layer stubbed out.

Skipped (not failed) in environments whose neuro-san predates the imports
get_mcp_tool needs, so the suite still collects everywhere.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest import mock

import pytest

pytest.importorskip("coded_tools.agent_network_editor.get_mcp_tool")

# The imports must stay below importorskip so old environments skip cleanly,
# and the tests reach the class's protected policy helpers by design.
# pylint: disable=wrong-import-position,protected-access
from coded_tools.agent_network_editor.get_mcp_tool import BUNDLED_MCP_INFO_FILE  # noqa: E402
from coded_tools.agent_network_editor.get_mcp_tool import DEFAULT_MCP_TOOLS_FETCH_TIMEOUT_SECONDS  # noqa: E402
from coded_tools.agent_network_editor.get_mcp_tool import DEFAULT_MCP_TOOLS_TTL_SECONDS  # noqa: E402
from coded_tools.agent_network_editor.get_mcp_tool import NSFLOW_MCP_TOKENS_FILE_NAME  # noqa: E402
from coded_tools.agent_network_editor.get_mcp_tool import GetMcpTool  # noqa: E402
from coded_tools.agent_network_editor.globals import ProcessGlobals  # noqa: E402

MCP_SERVERS: list[str] = ["https://one.example/mcp", "https://two.example/mcp"]

TTL_ENV: str = "AGENT_NETWORK_DESIGNER_MCP_TOOLS_TTL_SECONDS"
FETCH_TIMEOUT_ENV: str = "AGENT_NETWORK_DESIGNER_MCP_TOOLS_FETCH_TIMEOUT_SECONDS"
STORAGE_DIR_ENV: str = "NSFLOW_MCP_STORAGE_DIR"

# Points the nsflow token-store resolver away from any real ~/.nsflow on the
# machine running the tests; the file never exists, so the storage half of
# the servers union is empty unless a test writes its own store.
NO_TOKEN_STORE: dict[str, str] = {STORAGE_DIR_ENV: "/nonexistent/mcp_oauth"}


def write_token_store(directory: str, entries: dict) -> str:
    """Write a tokens.json with the given entries; returns the file path."""
    path = Path(directory) / NSFLOW_MCP_TOKENS_FILE_NAME
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


class TestGetMcpToolConfig(TestCase):
    """Validation policy for the env vars and the fingerprint they feed."""

    def test_ttl_falls_back_to_the_default_on_garbage(self):
        """Unset, unparseable, and non-finite TTLs all mean the default."""
        with mock.patch.dict(os.environ):
            os.environ.pop(TTL_ENV, None)
            os.environ.pop(FETCH_TIMEOUT_ENV, None)
            self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), DEFAULT_MCP_TOOLS_TTL_SECONDS)
            # nan and inf parse as floats but would silently freeze the
            # time bucket, so they are rejected alongside plain garbage.
            for raw in ("not-a-number", "nan", "inf", "-inf"):
                os.environ[TTL_ENV] = raw
                self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), DEFAULT_MCP_TOOLS_TTL_SECONDS)

    def test_ttl_of_zero_or_less_freezes_the_time_bucket(self):
        """<= 0 disables time-based refresh: no clamp, bucket pinned at 0."""
        with mock.patch.dict(os.environ):
            os.environ.pop(FETCH_TIMEOUT_ENV, None)
            for raw, expected in (("0", 0.0), ("-5", -5.0)):
                os.environ[TTL_ENV] = raw
                self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), expected)
                # The time bucket is the last fingerprint component.
                self.assertEqual(GetMcpTool._mcp_tools_fingerprint()[-1], 0)

    def test_ttl_is_clamped_to_twice_the_fetch_cap(self):
        """A TTL shorter than one fetch would livelock the cache; clamp it."""
        with mock.patch.dict(os.environ):
            os.environ.pop(FETCH_TIMEOUT_ENV, None)
            os.environ[TTL_ENV] = "5"
            self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), 2 * DEFAULT_MCP_TOOLS_FETCH_TIMEOUT_SECONDS)
            os.environ[FETCH_TIMEOUT_ENV] = "100"
            self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), 200.0)
            # With the cap disabled, the default cap is the clamp basis.
            os.environ[FETCH_TIMEOUT_ENV] = "0"
            self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), 2 * DEFAULT_MCP_TOOLS_FETCH_TIMEOUT_SECONDS)
            # A comfortable TTL is left alone.
            os.environ.pop(FETCH_TIMEOUT_ENV, None)
            os.environ[TTL_ENV] = "500"
            self.assertEqual(GetMcpTool._mcp_tools_ttl_seconds(), 500.0)

    def test_fetch_timeout_defaults_on_garbage_and_disables_below_zero(self):
        """Garbage means the default; <= 0 removes the cap entirely (None)."""
        with mock.patch.dict(os.environ):
            os.environ.pop(FETCH_TIMEOUT_ENV, None)
            self.assertEqual(GetMcpTool._mcp_tools_fetch_timeout_seconds(), DEFAULT_MCP_TOOLS_FETCH_TIMEOUT_SECONDS)
            os.environ[FETCH_TIMEOUT_ENV] = "120"
            self.assertEqual(GetMcpTool._mcp_tools_fetch_timeout_seconds(), 120.0)
            for raw in ("not-a-number", "nan", "inf"):
                os.environ[FETCH_TIMEOUT_ENV] = raw
                self.assertEqual(
                    GetMcpTool._mcp_tools_fetch_timeout_seconds(), DEFAULT_MCP_TOOLS_FETCH_TIMEOUT_SECONDS
                )
            for raw in ("0", "-1"):
                os.environ[FETCH_TIMEOUT_ENV] = raw
                self.assertIsNone(GetMcpTool._mcp_tools_fetch_timeout_seconds())

    def test_a_ttl_change_is_an_immediate_fingerprint_miss(self):
        """Bucket numbers from different TTL regimes must never compare equal."""
        with mock.patch.dict(os.environ):
            os.environ.pop(FETCH_TIMEOUT_ENV, None)
            os.environ[TTL_ENV] = "100000"
            before = GetMcpTool._mcp_tools_fingerprint()
            os.environ[TTL_ENV] = "50000"
            self.assertNotEqual(GetMcpTool._mcp_tools_fingerprint(), before)

    def test_a_deleted_cwd_falls_back_to_the_bundled_file(self):
        """get_mcp_info_file runs inside fingerprint probes; it must not raise."""
        with mock.patch.dict(os.environ):
            os.environ.pop("MCP_SERVERS_INFO_FILE", None)
            with mock.patch(
                "coded_tools.agent_network_editor.get_mcp_tool.Path.cwd",
                side_effect=FileNotFoundError("cwd was deleted"),
            ):
                self.assertEqual(GetMcpTool.get_mcp_info_file(), str(BUNDLED_MCP_INFO_FILE))


class TestGetMcpServers(TestCase):
    """Publish policy for the shared MCP-servers cache."""

    def setUp(self):
        # tests/conftest.py's autouse fixture also clears the shared caches
        # around every test; clearing here as well keeps these tests correct
        # when run directly through unittest.
        GetMcpTool.clear_shared_mcp_servers_for_testing()
        GetMcpTool.clear_shared_mcp_tool_descriptions_for_testing()
        # Keep the storage half hermetic: a real ~/.nsflow on the developer
        # machine must not leak servers into these assertions.
        env_patch = mock.patch.dict(os.environ, NO_TOKEN_STORE)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    @staticmethod
    def _patched_info_file(info: dict | None):
        """Patch the mcp_info.hocon half to parse to the given mapping."""
        restorer = mock.Mock()
        restorer.restore.return_value = info
        return mock.patch(
            "coded_tools.agent_network_editor.get_mcp_tool.McpServersInfoRestorer", return_value=restorer
        )

    def test_a_missing_file_publishes_an_empty_list(self):
        """No config file means no MCP servers, not an error."""
        with mock.patch.dict(os.environ, {"MCP_SERVERS_INFO_FILE": "/nonexistent/mcp_info.hocon"}):
            self.assertEqual(asyncio.run(GetMcpTool.get_mcp_servers()), [])

    def test_unreadable_and_unparseable_files_publish_an_empty_list(self):
        """OSError (unreadable) and ValueError (unparseable) both degrade to []."""
        for error in (OSError("permission denied"), ValueError("bad hocon")):
            GetMcpTool.clear_shared_mcp_servers_for_testing()
            restorer = mock.Mock()
            restorer.restore.side_effect = error
            with mock.patch(
                "coded_tools.agent_network_editor.get_mcp_tool.McpServersInfoRestorer", return_value=restorer
            ):
                self.assertEqual(asyncio.run(GetMcpTool.get_mcp_servers()), [])

    def test_servers_are_the_union_of_file_and_storage(self):
        """mcp_info.hocon URLs and nsflow OAuth connections merge into one list."""
        info = {MCP_SERVERS[0]: {"http_headers": {"X-Api-Key": "from-env"}}}
        with tempfile.TemporaryDirectory() as storage_dir:
            write_token_store(storage_dir, {MCP_SERVERS[1]: {"tokens": {"access_token": "tok-1"}}})
            with mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}), self._patched_info_file(info):
                self.assertEqual(sorted(asyncio.run(GetMcpTool.get_mcp_servers())), sorted(MCP_SERVERS))

    def test_a_storage_entry_without_an_access_token_is_not_a_server(self):
        """Pre-seeded client_info, corrupt entries, and empty tokens don't count."""
        entries = {
            "https://client-info-only.example/mcp": {"client_info": {"client_id": "abc"}},
            "https://corrupt.example/mcp": "not-a-dict",
            "https://empty-token.example/mcp": {"tokens": {"access_token": ""}},
            MCP_SERVERS[0]: {"tokens": {"access_token": "tok-0"}},
        }
        with tempfile.TemporaryDirectory() as storage_dir:
            write_token_store(storage_dir, entries)
            with mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}), self._patched_info_file(None):
                self.assertEqual(asyncio.run(GetMcpTool.get_mcp_servers()), [MCP_SERVERS[0]])

    def test_a_token_store_rewrite_is_a_fingerprint_miss(self):
        """A new OAuth connection (tokens.json write) must invalidate the cache."""
        with tempfile.TemporaryDirectory() as storage_dir:
            with mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}):
                before = GetMcpTool._mcp_sources_fingerprint()
                tokens_file = write_token_store(storage_dir, {MCP_SERVERS[0]: {"tokens": {"access_token": "tok"}}})
                after = GetMcpTool._mcp_sources_fingerprint()
        self.assertNotEqual(before, after)
        self.assertEqual(after[2], tokens_file)


class TestNsflowTokenStorage(TestCase):
    """Read policy for nsflow's tokens.json: tolerant, attempt-and-drop."""

    def test_a_missing_store_reads_as_empty(self):
        """No tokens.json just means nsflow has no connections — no error."""
        with mock.patch.dict(os.environ, NO_TOKEN_STORE):
            self.assertEqual(GetMcpTool._load_storage_access_tokens(), {})

    def test_corrupt_json_and_a_non_object_top_level_read_as_empty(self):
        """A hand-edited or truncated store degrades to {} instead of raising."""
        for content in ("{not json", '["a", "list"]', '"just a string"'):
            with tempfile.TemporaryDirectory() as storage_dir:
                Path(storage_dir, NSFLOW_MCP_TOKENS_FILE_NAME).write_text(content, encoding="utf-8")
                with mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}):
                    self.assertEqual(GetMcpTool._load_storage_access_tokens(), {})

    def test_needs_reauth_and_expired_entries_are_still_read(self):
        """Attempt-and-drop: stale tokens are tried (and fail downstream), not filtered."""
        entries = {
            MCP_SERVERS[0]: {"tokens": {"access_token": "stale"}, "needs_reauth": True, "expires_at": 1},
        }
        with tempfile.TemporaryDirectory() as storage_dir:
            write_token_store(storage_dir, entries)
            with mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}):
                self.assertEqual(GetMcpTool._load_storage_access_tokens(), {MCP_SERVERS[0]: "stale"})

    def test_the_storage_dir_env_var_is_respected_and_expanded(self):
        """The resolver honors NSFLOW_MCP_STORAGE_DIR and expands ~."""
        with mock.patch.dict(os.environ, {STORAGE_DIR_ENV: "~/custom_mcp_store"}):
            resolved = GetMcpTool.get_nsflow_tokens_file()
        self.assertEqual(resolved, str(Path("~/custom_mcp_store").expanduser() / NSFLOW_MCP_TOKENS_FILE_NAME))
        with mock.patch.dict(os.environ):
            os.environ.pop(STORAGE_DIR_ENV, None)
            default_resolved = GetMcpTool.get_nsflow_tokens_file()
        self.assertEqual(default_resolved, str(Path("~/.nsflow/mcp_oauth").expanduser() / NSFLOW_MCP_TOKENS_FILE_NAME))


class TestGetMcpServersAuthInfo(TestCase):
    """The url -> needs-client-token view that drives generated sly_data_schema."""

    def setUp(self):
        GetMcpTool.clear_shared_mcp_servers_for_testing()
        GetMcpTool.clear_shared_mcp_tool_descriptions_for_testing()

    def test_info_file_servers_need_no_client_token(self):
        """mcp_info.hocon servers are a server-side concern — with headers or without."""
        info = {
            MCP_SERVERS[0]: {"http_headers": {"X-Api-Key": "from-env"}},
            MCP_SERVERS[1]: {},  # public/no-auth file server: still not a client concern
        }
        with tempfile.TemporaryDirectory() as storage_dir:
            write_token_store(storage_dir, {"https://oauth-only.example/mcp": {"tokens": {"access_token": "tok"}}})
            with (
                mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}),
                TestGetMcpServers._patched_info_file(info),
            ):
                auth_info = asyncio.run(GetMcpTool.get_mcp_servers_auth_info())

        self.assertEqual(
            auth_info,
            {
                MCP_SERVERS[0]: False,
                MCP_SERVERS[1]: False,
                "https://oauth-only.example/mcp": True,
            },
        )
        for value in auth_info.values():
            self.assertIsInstance(value, bool)

    def test_a_stored_token_does_not_flip_an_info_file_server(self):
        """A URL in both sources stays a server-side concern (no client gating)."""
        info = {MCP_SERVERS[0]: {"http_headers": {"Authorization": "Bearer from-env"}}}
        with tempfile.TemporaryDirectory() as storage_dir:
            write_token_store(storage_dir, {MCP_SERVERS[0]: {"tokens": {"access_token": "tok"}}})
            with (
                mock.patch.dict(os.environ, {STORAGE_DIR_ENV: storage_dir}),
                TestGetMcpServers._patched_info_file(info),
            ):
                auth_info = asyncio.run(GetMcpTool.get_mcp_servers_auth_info())
        self.assertEqual(auth_info, {MCP_SERVERS[0]: False})


class TestGetMcpToolDescriptions(TestCase):
    """Publish/degrade policy for the shared tool-descriptions cache."""

    def setUp(self):
        GetMcpTool.clear_shared_mcp_servers_for_testing()
        GetMcpTool.clear_shared_mcp_tool_descriptions_for_testing()
        env_patch = mock.patch.dict(os.environ, NO_TOKEN_STORE)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.fetch_log: list[str] = []
        self.headers_log: dict[str, dict | None] = {}
        self.listings: dict[str, str] = {server: f"tools of {server}" for server in MCP_SERVERS}

    def _patched_fetches(self):
        """Stub the per-server fetch; a server absent from self.listings fails."""
        fetch_log = self.fetch_log
        headers_log = self.headers_log
        listings = self.listings

        async def fake_fetch(
            server: str, _fetch_timeout: float | None, headers: dict | None = None
        ) -> tuple[str, str | None]:
            fetch_log.append(server)
            headers_log[server] = headers
            return server, listings.get(server)

        return mock.patch.object(GetMcpTool, "_fetch_tool_descriptions", new=fake_fetch)

    def _patched_servers(self, servers: list[str] | None = None, tokens: dict[str, str] | None = None):
        """Pin the servers half so these tests never read the real config file."""
        pinned = MCP_SERVERS if servers is None else servers
        tokens = tokens or {}
        infos: dict[str, dict] = {
            server: {"has_file_headers": False, "access_token": tokens.get(server)} for server in pinned
        }
        return mock.patch.object(GetMcpTool._shared_mcp_servers_cache, "get", new=mock.Mock(return_value=infos))

    def test_concurrent_callers_share_one_fetch_and_warm_reads_are_free(self):
        """A cold burst fetches each server once; warm reads fetch nothing."""

        async def run() -> list[dict[str, str]]:
            burst = await asyncio.gather(*[GetMcpTool.get_mcp_tool_descriptions() for _ in range(10)])
            warm = await GetMcpTool.get_mcp_tool_descriptions()
            return burst + [warm]

        with mock.patch.dict(os.environ, {TTL_ENV: "100000"}), self._patched_servers(), self._patched_fetches():
            results = asyncio.run(run())

        for result in results:
            self.assertEqual(result, self.listings)
        # One fetch per server for the whole burst, none for the warm read.
        self.assertEqual(sorted(self.fetch_log), sorted(MCP_SERVERS))

    def test_a_failed_server_is_omitted_and_the_partial_result_is_published(self):
        """One dead server hides that server only, and only until the TTL rolls."""
        del self.listings[MCP_SERVERS[1]]

        async def run() -> tuple[dict[str, str], dict[str, str]]:
            return await GetMcpTool.get_mcp_tool_descriptions(), await GetMcpTool.get_mcp_tool_descriptions()

        with mock.patch.dict(os.environ, {TTL_ENV: "100000"}), self._patched_servers(), self._patched_fetches():
            first, second = asyncio.run(run())

        self.assertEqual(first, self.listings)
        self.assertEqual(second, self.listings)
        # The partial result was published: one fetch per server, total.
        self.assertEqual(sorted(self.fetch_log), sorted(MCP_SERVERS))

    def test_all_failed_with_frozen_ttl_degrades_per_call_and_heals(self):
        """With refresh disabled, an all-failed fetch must not be pinned forever."""
        healthy = dict(self.listings)
        self.listings.clear()

        with mock.patch.dict(os.environ, {TTL_ENV: "0"}), self._patched_servers(), self._patched_fetches():
            self.assertEqual(asyncio.run(GetMcpTool.get_mcp_tool_descriptions()), {})
            # Nothing was published: the moment the servers answer again,
            # callers get the full mapping — no fingerprint change needed.
            self.listings.update(healthy)
            self.assertEqual(asyncio.run(GetMcpTool.get_mcp_tool_descriptions()), healthy)

    def test_all_failed_with_a_live_ttl_is_published_for_the_window(self):
        """With refresh enabled, publishing {} prevents a per-call fetch storm."""
        self.listings.clear()

        async def run() -> tuple[dict[str, str], dict[str, str]]:
            return await GetMcpTool.get_mcp_tool_descriptions(), await GetMcpTool.get_mcp_tool_descriptions()

        with mock.patch.dict(os.environ, {TTL_ENV: "100000"}), self._patched_servers(), self._patched_fetches():
            first, second = asyncio.run(run())

        self.assertEqual((first, second), ({}, {}))
        # The empty result was published: the second call fetched nothing.
        self.assertEqual(sorted(self.fetch_log), sorted(MCP_SERVERS))

    def test_no_configured_servers_publishes_empty_even_when_frozen(self):
        """An empty server list is a fact, not a failure — publish it."""
        with mock.patch.dict(os.environ, {TTL_ENV: "0"}), self._patched_servers([]), self._patched_fetches():
            self.assertEqual(asyncio.run(GetMcpTool.get_mcp_tool_descriptions()), {})
            self.assertEqual(asyncio.run(GetMcpTool.get_mcp_tool_descriptions()), {})
        self.assertEqual(self.fetch_log, [])

    def test_returned_mapping_is_a_copy(self):
        """Mutating a returned mapping must not corrupt the shared value."""

        async def run() -> dict[str, str]:
            first = await GetMcpTool.get_mcp_tool_descriptions()
            first["https://tampered.example"] = "oops"
            return await GetMcpTool.get_mcp_tool_descriptions()

        with mock.patch.dict(os.environ, {TTL_ENV: "100000"}), self._patched_servers(), self._patched_fetches():
            second = asyncio.run(run())

        self.assertNotIn("https://tampered.example", second)

    def test_async_invoke_renders_the_mapping_as_a_string(self):
        """The coded-tool entry point returns str(mapping), per its contract."""
        tool: GetMcpTool = GetMcpTool.__new__(GetMcpTool)

        with mock.patch.dict(os.environ, {TTL_ENV: "100000"}), self._patched_servers(), self._patched_fetches():
            result = asyncio.run(tool.async_invoke(args={}, sly_data={}))

        self.assertEqual(result, str(self.listings))

    def test_a_storage_token_is_sent_as_a_bearer_header(self):
        """A server with a stored nsflow token gets it as an Authorization header."""
        tokens = {MCP_SERVERS[0]: "tok-0"}

        with (
            mock.patch.dict(os.environ, {TTL_ENV: "100000"}),
            self._patched_servers(tokens=tokens),
            self._patched_fetches(),
        ):
            result = asyncio.run(GetMcpTool.get_mcp_tool_descriptions())

        self.assertEqual(self.headers_log[MCP_SERVERS[0]], {"Authorization": "Bearer tok-0"})
        # A server with no stored token keeps headers=None, preserving the
        # adapter's fallback to mcp_info.hocon http_headers.
        self.assertIsNone(self.headers_log[MCP_SERVERS[1]])
        # The token itself never surfaces in what the LLM will see.
        self.assertNotIn("tok-0", str(result))

    def test_registry_covers_both_mcp_caches(self):
        """globals' REGISTRY triples must resolve now that get_mcp_tool is imported."""
        with mock.patch.dict(os.environ, {TTL_ENV: "100000"}), self._patched_servers(), self._patched_fetches():
            asyncio.run(GetMcpTool.get_mcp_tool_descriptions())
            cache = GetMcpTool._shared_mcp_tool_descriptions_cache
            self.assertIsNotNone(cache.peek())
            # A typo'd module/class/method triple would raise here.
            ProcessGlobals.clear_all_for_testing()
            self.assertIsNone(cache.peek())


class TestFetchToolDescriptions(TestCase):
    """The per-server fetch: cap applied, failures contained, success flattened."""

    @staticmethod
    def _patched_adapter(get_mcp_tools):
        """Patch the MCP adapter with a stub serving the given coroutine function."""
        adapter = mock.Mock()
        adapter.get_mcp_tools = get_mcp_tools
        return mock.patch("coded_tools.agent_network_editor.get_mcp_tool.LangChainMcpAdapter", return_value=adapter)

    def test_a_server_exceeding_the_cap_degrades_to_a_failure(self):
        """A hung server is cut off at the cap and reported as failed."""

        async def never_answers(_server: str, headers: dict | None = None) -> list:  # pylint: disable=unused-argument
            await asyncio.sleep(10)
            return []

        with self._patched_adapter(never_answers):
            server, description = asyncio.run(GetMcpTool._fetch_tool_descriptions("https://slow.example", 0.05))

        self.assertEqual(server, "https://slow.example")
        self.assertIsNone(description)

    def test_a_malformed_tool_degrades_to_that_server_only(self):
        """A tool with no description must fail this server, not the whole load."""

        async def returns_a_broken_tool(  # pylint: disable=unused-argument
            _server: str, headers: dict | None = None
        ) -> list:
            return [mock.Mock(description=None)]

        with self._patched_adapter(returns_a_broken_tool):
            _server, description = asyncio.run(GetMcpTool._fetch_tool_descriptions("https://bad.example", 5.0))

        self.assertIsNone(description)

    def test_descriptions_are_newline_joined(self):
        """A healthy server's tool descriptions flatten into one string."""

        async def returns_two_tools(  # pylint: disable=unused-argument
            _server: str, headers: dict | None = None
        ) -> list:
            return [mock.Mock(description="alpha"), mock.Mock(description="beta")]

        with self._patched_adapter(returns_two_tools):
            _server, description = asyncio.run(GetMcpTool._fetch_tool_descriptions("https://good.example", 5.0))

        self.assertEqual(description, "alpha\nbeta\n")

    def test_headers_are_forwarded_to_the_adapter(self):
        """The per-server fetch passes its headers through to get_mcp_tools."""
        seen: dict[str, dict | None] = {}

        async def records_headers(server: str, headers: dict | None = None) -> list:
            seen[server] = headers
            return [mock.Mock(description="alpha")]

        with self._patched_adapter(records_headers):
            asyncio.run(
                GetMcpTool._fetch_tool_descriptions(
                    "https://auth.example", 5.0, headers={"Authorization": "Bearer tok"}
                )
            )

        self.assertEqual(seen["https://auth.example"], {"Authorization": "Bearer tok"})
