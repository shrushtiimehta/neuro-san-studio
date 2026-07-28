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
Generic process-wide, load-once cache for expensive shared values.

This is the one copy of the locking and publish discipline that the Agent
Network Designer family's shared caches were previously each hand-rolling
(ConnectivityDictionaryConverter's ToolboxFactory for issue #1262, GetToolbox's
toolbox info for #1268, GetSubnetwork's subnetwork names for #1267). Each
owning class keeps its public peek/get/clear_for_testing API and delegates to
an instance of this class, so all cache *policy* stays visible on the owner
while the subtle *mechanism* lives here once.
"""

from asyncio import Task
from asyncio import get_running_loop
from asyncio import shield
from asyncio import to_thread
from threading import Lock
from typing import Any
from typing import Callable
from typing import Generic
from typing import TypeVar
from weakref import WeakKeyDictionary

T = TypeVar("T")


class SharedProcessCache(Generic[T]):
    """
    Process-wide cache of a single expensive value, safe across threads and
    event loops.

    * loader: synchronous callable producing the value. It runs under the
      cache lock — and in a worker thread when reached through aget() — so it
      may do blocking file I/O and CPU-heavy parsing. It must either return a
      complete, ready-to-share value or raise; on a raise nothing is
      published, so the next call retries instead of serving a half-built or
      failure value. Loaders must not return None (return an empty container
      instead) — None is the cache's "not loaded" sentinel.
    * fingerprint: optional cheap callable identifying the version of the
      source the value was built from (e.g. a (path, mtime) tuple, which can
      also fold in a time bucket for TTL-style expiry). It is captured just
      BEFORE the loader runs and re-checked on every read; when the current
      fingerprint no longer matches the stored one, the entry is treated as a
      miss and reloaded. It must be lock-free-safe and must not raise. When
      None, the value is loaded once and lives for the life of the process.

    Concurrency notes (the reasoning previously duplicated per cache):
    * The guard is a threading.Lock rather than an asyncio.Lock because
      callers may run on different event loops in different threads, and an
      asyncio.Lock cannot be shared across event loops.
    * The warm path takes no lock: the entry is a single attribute written
      exactly once per load, only after the loader fully succeeded, and
      CPython reference reads are atomic under the GIL — so a non-None read
      always yields a complete (value, fingerprint) pair. Do not reorder the
      publish in get().
    * aget() keeps the cold load off the event loop via asyncio.to_thread()
      and funnels concurrent cold callers on the same loop into ONE load: the
      first caller creates the load task and the rest await it, so a cold
      burst cannot fill the loop's default executor with lock-waiters. The
      await is shield()-ed, so one cancelled caller cannot cancel the shared
      load out from under the others.
    """

    def __init__(self, loader: Callable[[], T], fingerprint: Callable[[], Any] | None = None):
        """
        Constructor

        :param loader: Synchronous callable that builds the value. See the
                class docstring for its contract.
        :param fingerprint: Optional source-version probe. See the class
                docstring for its contract.
        """
        self._loader = loader
        self._fingerprint = fingerprint
        # The one shared slot: None, or a (value, fingerprint-at-load) pair
        # stored as a single tuple so lock-free readers see it atomically.
        self._entry: tuple[T, Any] | None = None
        self._lock = Lock()
        # Per-event-loop in-flight load task, so concurrent async callers on
        # one loop share a single to_thread() dispatch. Entries are removed
        # by each task's done callback (_forget_in_flight_load) — the weak
        # keying alone cannot reclaim them, because a Task strongly
        # references the loop it runs on, i.e. its own key. Access races
        # between loops are benign: at worst two loops each run a load, and
        # the lock in get() still serializes the actual work.
        self._loads_in_flight: WeakKeyDictionary = WeakKeyDictionary()

    def peek(self) -> T | None:
        """
        :return: The cached value if it is present and still fresh per the
                fingerprint, else None. Lock-free and safe to call from any
                thread or event loop; async callers can use a None result to
                decide to reach get() through a worker thread. Treat the
                result as read-only unless the owner documents otherwise — it
                is the live shared value, not a copy.
        """
        entry: tuple[T, Any] | None = self._entry
        if entry is None:
            return None
        value, loaded_fingerprint = entry
        if self._fingerprint is not None and self._fingerprint() != loaded_fingerprint:
            # The source moved on since this value was built: report a miss
            # and leave the stale entry in place for get() to replace.
            return None
        return value

    def get(self) -> T:
        """
        Get the value, running the loader on a miss (first call in the
        process, or the fingerprint went stale).

        Blocking: the loader may do file I/O and parsing, so async callers
        must not call this on the event loop — use aget(), or peek() first
        and reach this via asyncio.to_thread().

        :return: The cached or freshly loaded value. Loader exceptions
                propagate without publishing anything, so the next call
                retries.
        """
        value: T | None = self.peek()
        if value is not None:
            return value

        with self._lock:
            # Double-check under the lock: another thread may have loaded
            # while this one waited.
            value = self.peek()
            if value is not None:
                return value

            # Capture the fingerprint BEFORE loading: if the source changes
            # while the loader runs, the next read's probe mismatches and the
            # value is rebuilt, rather than a torn read living forever.
            loaded_fingerprint: Any = self._fingerprint() if self._fingerprint is not None else None
            value = self._loader()
            # Publish only after the loader fully succeeded. Do not reorder.
            self._entry = (value, loaded_fingerprint)

        return value

    async def aget(self) -> T:
        """
        Async get(): warm reads return via the lock-free peek with no
        awaiting at all; a cold load runs in a worker thread, shared by every
        concurrent cold caller on this event loop.

        :return: The cached or freshly loaded value. Loader exceptions
                propagate to every caller awaiting that load, and the next
                aget() starts a fresh attempt.
        """
        value: T | None = self.peek()
        if value is not None:
            return value

        loop = get_running_loop()
        task: Task | None = self._loads_in_flight.get(loop)
        if task is None or task.done():
            # A done task is a finished earlier attempt (possibly failed or
            # stale); start a new one. Awaiters of the old task are unaffected.
            task = loop.create_task(to_thread(self.get))
            self._loads_in_flight[loop] = task
            task.add_done_callback(self._forget_in_flight_load)
        # shield() detaches awaiter cancellation from the shared task: a
        # cancelled awaiter still gets its CancelledError, but the load keeps
        # running and completes for the other awaiters. An unshielded await
        # here would let one cancelled caller cancel everyone else's load,
        # because Task.cancel() propagates into whatever the task is awaiting.
        return await shield(task)

    def _forget_in_flight_load(self, task: Task):
        """
        Done-callback for once-gate load tasks (see aget()).

        Dropping the finished task promptly matters beyond tidiness: a Task
        strongly references the event loop it runs on — its own dictionary
        key — so entries would otherwise never be garbage-collected despite
        the weak keying, leaking one loop + task per event loop under
        loop-per-test runners. Retrieving the exception keeps a failed load
        whose awaiters were all cancelled from logging "Task exception was
        never retrieved".
        """
        loop = task.get_loop()
        # Only forget the task this callback belongs to: clear_for_testing()
        # may have dropped it already. pop() instead of del so a concurrent
        # clear between the check and the removal stays a no-op; a *newer*
        # task cannot sneak into the slot in that window, because only this
        # loop's thread installs tasks for this key.
        if self._loads_in_flight.get(loop) is task:
            self._loads_in_flight.pop(loop, None)
        if not task.cancelled():
            # Mark a failed load's exception as retrieved (returns None on
            # success). Awaiters that were still around received it via the
            # shield()-ed await.
            task.exception()

    def clear_for_testing(self):
        """
        Drop the cached value and forget any in-flight once-gate loads. For
        test isolation only — production code relies on load-once semantics.

        Forgetting the in-flight tasks matters: without it, an aget() issued
        after the clear could adopt a still-pending pre-clear load and
        receive a value built under the previous test's env/file state. The
        lock serializes this reset with a load that is mid-publish; a
        pre-clear load that was dispatched but never awaited can still
        publish after the reset, which tests avoid by running loads
        sequentially.
        """
        # Taking the lock serializes the reset with a concurrent load, so
        # this can never unpublish an entry mid-initialization.
        with self._lock:
            self._entry = None
            self._loads_in_flight.clear()
