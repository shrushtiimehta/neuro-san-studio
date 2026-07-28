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
Tests for SharedProcessCache and the process-globals registry.

Deliberately stdlib-only (no neuro-san imports): the cache is the shared
concurrency mechanism under every process-wide cache in the Agent Network
Designer family, so these tests must run in any environment that can
collect the suite. Async cases drive their own event loops via asyncio.run()
rather than depending on an asyncio pytest plugin.
"""

import asyncio
import sys
import threading
import time
import types

import pytest

from coded_tools.agent_network_editor import globals as process_globals
from coded_tools.agent_network_editor.shared_process_cache import SharedProcessCache


def test_get_loads_once_and_peek_reflects_state():
    """Loader runs once; peek() mirrors loaded/unloaded state."""
    calls: list[int] = []

    def loader() -> str:
        calls.append(1)
        return "value"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader)
    assert cache.peek() is None
    assert cache.get() == "value"
    assert cache.get() == "value"
    assert cache.peek() == "value"
    assert len(calls) == 1


def test_loader_failure_publishes_nothing_and_next_call_retries():
    """A raising loader publishes nothing, so the next get() retries."""
    attempts = {"count": 0}

    def loader() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("boom")
        return "healed"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader)
    with pytest.raises(RuntimeError):
        cache.get()
    assert cache.peek() is None
    assert cache.get() == "healed"
    assert attempts["count"] == 2


def test_fingerprint_controls_freshness():
    """A fingerprint change turns warm reads into a miss and reload."""
    source = {"fingerprint": 1, "loads": 0}

    def loader() -> str:
        source["loads"] += 1
        return f"value-{source['fingerprint']}"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader, fingerprint=lambda: source["fingerprint"])
    assert cache.get() == "value-1"
    assert cache.get() == "value-1"
    assert source["loads"] == 1

    # The source moved on: peek() reports a miss and get() rebuilds.
    source["fingerprint"] = 2
    assert cache.peek() is None
    assert cache.get() == "value-2"
    assert source["loads"] == 2


def test_fingerprint_is_captured_before_the_loader_runs():
    """A mid-load source change leaves the published entry stale."""
    # If the source changes while the loader runs, the published entry must
    # already be stale so the next read rebuilds it instead of a torn value
    # living forever.
    source = {"fingerprint": 1}

    def loader() -> str:
        source["fingerprint"] = 2
        return "torn"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader, fingerprint=lambda: source["fingerprint"])
    assert cache.get() == "torn"
    assert cache.peek() is None


def test_aget_shares_one_load_across_concurrent_cold_callers():
    """Concurrent cold aget() callers share a single loader run."""
    calls = {"count": 0}

    def loader() -> str:
        calls["count"] += 1
        time.sleep(0.05)
        return "shared"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader)

    async def run() -> list[str]:
        return await asyncio.gather(*[cache.aget() for _ in range(20)])

    assert asyncio.run(run()) == ["shared"] * 20
    assert calls["count"] == 1


def test_aget_load_survives_one_awaiter_being_cancelled():
    """Cancelling one aget() awaiter must not cancel the shared load."""
    # Regression test for the unshielded await: cancelling one awaiter must
    # not cancel the shared load out from under the other awaiters.
    loader_started = threading.Event()
    release_loader = threading.Event()

    def loader() -> str:
        loader_started.set()
        release_loader.wait(timeout=5)
        return "survived"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader)

    async def run() -> str:
        first = asyncio.create_task(cache.aget())
        second = asyncio.create_task(cache.aget())
        await asyncio.to_thread(loader_started.wait, 5)
        first.cancel()
        release_loader.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        return await second

    assert asyncio.run(run()) == "survived"


def test_aget_failure_is_shared_and_next_call_retries():
    """A failing shared load raises for all awaiters; next aget() retries."""
    attempts = {"count": 0}

    def loader() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("boom")
        return "healed"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader)

    async def run() -> str:
        results = await asyncio.gather(*[cache.aget() for _ in range(3)], return_exceptions=True)
        assert all(isinstance(result, RuntimeError) for result in results)
        return await cache.aget()

    assert asyncio.run(run()) == "healed"
    assert attempts["count"] == 2


def test_aget_cleans_up_in_flight_bookkeeping_across_event_loops():
    """The once-gate map must not pin dead event loops (leak regression)."""
    # Regression test for the once-gate leak: a Task strongly references the
    # event loop it runs on (its own dictionary key), so without the done
    # callback the weak keying never reclaims entries and one loop + task
    # would be pinned per event loop that ever cold-loaded.
    cache: SharedProcessCache[str] = SharedProcessCache(loader=lambda: "value")
    for _ in range(5):
        cache.clear_for_testing()
        assert asyncio.run(cache.aget()) == "value"
    assert len(cache._loads_in_flight) == 0  # pylint: disable=protected-access


def test_clear_for_testing_drops_entry_and_pending_loads():
    """clear_for_testing() drops the entry AND forgets pending loads."""
    calls = {"count": 0}

    def loader() -> str:
        calls["count"] += 1
        return f"load-{calls['count']}"

    cache: SharedProcessCache[str] = SharedProcessCache(loader=loader)
    assert cache.get() == "load-1"

    async def run() -> str:
        loop = asyncio.get_running_loop()
        # Stand-in for a load still in flight when the clear happens: if
        # clear_for_testing() left it behind, aget() would adopt it (it is
        # not done) and time out below instead of starting a fresh load.
        pending = loop.create_task(asyncio.sleep(60))
        cache._loads_in_flight[loop] = pending  # pylint: disable=protected-access
        cache.clear_for_testing()
        assert cache.peek() is None
        value = await asyncio.wait_for(cache.aget(), timeout=5)
        pending.cancel()
        return value

    assert asyncio.run(run()) == "load-2"


def test_clear_all_process_globals_clears_imported_and_skips_unimported(monkeypatch):
    """The registry clears imported owners and skips unimported ones."""
    cleared: list[str] = []

    class FakeOwner:  # pylint: disable=too-few-public-methods
        """Stand-in owner class exposing a clear method like the real caches."""

        @classmethod
        def clear_fake_for_testing(cls):
            """Record that the registry reached this clear method."""
            cleared.append("cleared")

    fake_module = types.ModuleType("fake_process_globals_owner_module")
    fake_module.FakeOwner = FakeOwner
    monkeypatch.setitem(sys.modules, "fake_process_globals_owner_module", fake_module)
    monkeypatch.setattr(
        process_globals,
        "PROCESS_GLOBALS",
        [
            ("fake_process_globals_owner_module", "FakeOwner", "clear_fake_for_testing"),
            # Never imported: must be skipped silently (an unimported module
            # cannot have a populated cache), not raise.
            ("module_that_was_never_imported_for_test", "Nope", "clear_nope_for_testing"),
        ],
    )

    process_globals.clear_all_process_globals_for_testing()
    assert cleared == ["cleared"]


def test_process_globals_registry_entries_resolve_when_imported():
    """Registry triples must resolve against any imported owner module."""
    for module_name, class_name, clear_method_name in process_globals.PROCESS_GLOBALS:
        assert module_name.startswith("coded_tools.")
        # Owner modules need neuro-san, so only validate the ones this test
        # run happens to have imported; a typo'd class or method name in an
        # imported module must fail here rather than being skipped silently.
        module = sys.modules.get(module_name)
        if module is not None:
            assert callable(getattr(getattr(module, class_name), clear_method_name))
