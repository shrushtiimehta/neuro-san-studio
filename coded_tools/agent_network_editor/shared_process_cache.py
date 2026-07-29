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
(ConnectivityDictionaryConverter's ToolboxFactory, GetToolbox's toolbox info,
GetSubnetwork's subnetwork names). Each owning class keeps its public
accessors and clear_*_for_testing API and delegates to an instance of this
class, so all cache *policy* stays visible on the owner while the subtle
*mechanism* lives here once.
"""

from asyncio import Task
from asyncio import get_running_loop
from asyncio import shield
from asyncio import to_thread
from threading import Lock
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Generic
from typing import TypeVar
from weakref import WeakKeyDictionary

CachedValue = TypeVar("CachedValue")


class SharedProcessCache(Generic[CachedValue]):
    """
    Process-wide cache of a single expensive value, safe across threads and
    event loops.

    * loader: optional synchronous callable producing the value. It runs
      under the cache lock — and in a worker thread when reached through
      aget() — so it may do blocking file I/O and CPU-heavy parsing. It must
      either return a complete, ready-to-share value or raise; on a raise
      nothing is published, so the next call retries instead of serving a
      half-built or failure value. Loaders must not return None (return an
      empty container instead) — None is the cache's "not loaded" sentinel.
      When the value can only be built from context that exists at the call
      site (e.g. a request-scoped session factory that no standalone loader
      could reach), construct the cache without a loader and fill it through
      aget_or_fill() instead; get() and aget() then raise on a miss.
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
    * aget_or_fill() applies the same discipline to values built by an async
      callable ON the event loop: same once-gate, same capture-fingerprint-
      before-building, same publish-only-on-success. Because a threading.Lock
      cannot be held across an await, its miss double-check is lock-free and
      only the publish takes the lock — so two loops can race to fill, which
      is benign: each publishes a complete value under an equally current
      fingerprint, and the race costs one duplicate build. Do not combine it
      with a blocking loader on the same instance: get() holds the lock for
      the whole load, and aget_or_fill()'s publish would then block its
      event loop waiting for that lock.
    """

    def __init__(self, loader: Callable[[], CachedValue] | None = None, fingerprint: Callable[[], Any] | None = None):
        """
        Constructor

        :param loader: Optional synchronous callable that builds the value.
                See the class docstring for its contract; omit it for caches
                filled at the call site via aget_or_fill().
        :param fingerprint: Optional source-version probe. See the class
                docstring for its contract.
        """
        self._loader = loader
        self._fingerprint = fingerprint
        # The one shared slot: None, or a (value, fingerprint-at-load) pair
        # stored as a single tuple so lock-free readers see it atomically.
        self._entry: tuple[CachedValue, Any] | None = None
        self._lock = Lock()
        # Per-event-loop in-flight load task, so concurrent async callers on
        # one loop share a single to_thread() dispatch. Entries are removed
        # by each task's done callback (_forget_in_flight_load) — the weak
        # keying alone cannot reclaim them, because a Task strongly
        # references the loop it runs on, i.e. its own key. Access races
        # between loops are benign: at worst two loops each run a load, and
        # the lock in get() still serializes the actual work.
        self._loads_in_flight: WeakKeyDictionary = WeakKeyDictionary()

    def peek(self) -> CachedValue | None:
        """
        :return: The cached value if it is present and still fresh per the
                fingerprint, else None. Lock-free and safe to call from any
                thread or event loop; async callers can use a None result to
                decide to reach get() through a worker thread. Treat the
                result as read-only unless the owner documents otherwise — it
                is the live shared value, not a copy.
        """
        entry: tuple[CachedValue, Any] | None = self._entry
        if entry is None:
            return None
        value, loaded_fingerprint = entry
        if self._fingerprint is not None and self._fingerprint() != loaded_fingerprint:
            # The source moved on since this value was built: report a miss
            # and leave the stale entry in place for get() to replace.
            return None
        return value

    def get(self) -> CachedValue:
        """
        Get the value, running the loader on a miss (first call in the
        process, or the fingerprint went stale).

        Blocking: the loader may do file I/O and parsing, so async callers
        must not call this on the event loop — use aget(), or peek() first
        and reach this via asyncio.to_thread().

        :return: The cached or freshly loaded value. Loader exceptions
                propagate without publishing anything, so the next call
                retries. A miss on a cache constructed without a loader
                raises RuntimeError — such a cache is filled at the call
                site via aget_or_fill().
        """
        value: CachedValue | None = self.peek()
        if value is not None:
            return value

        with self._lock:
            # Probe the fingerprint once per miss: it serves both as the
            # double-check against a load that finished while this thread
            # waited for the lock, and as the freshness capture stored with
            # the value below — so a stat-style probe runs once, not twice.
            current_fingerprint: Any = self._fingerprint() if self._fingerprint is not None else None
            entry: tuple[CachedValue, Any] | None = self._entry
            if entry is not None and (self._fingerprint is None or entry[1] == current_fingerprint):
                return entry[0]

            if self._loader is None:
                raise RuntimeError(
                    "SharedProcessCache miss on a cache with no loader; "
                    "this cache can only be filled via aget_or_fill()."
                )

            # The fingerprint was captured BEFORE loading: if the source
            # changes while the loader runs, the next read's probe mismatches
            # and the value is rebuilt, rather than a torn read living forever.
            value = self._loader()
            # Publish only after the loader fully succeeded. Do not reorder.
            self._entry = (value, current_fingerprint)

        return value

    async def aget(self) -> CachedValue:
        """
        Async get(): warm reads resolve via the lock-free peek without
        suspending the caller (the await completes immediately); a cold load
        runs in a worker thread, shared by every concurrent cold caller on
        this event loop.

        :return: The cached or freshly loaded value. Loader exceptions
                propagate to every caller awaiting that load, and the next
                aget() starts a fresh attempt.
        """
        value: CachedValue | None = self.peek()
        if value is not None:
            return value

        return await self._await_shared_load(lambda: to_thread(self.get))

    async def aget_or_fill(self, filler: Callable[[], Awaitable[CachedValue]]) -> CachedValue:
        """
        aget() for caches whose value can only be built from context that
        exists at the call site (e.g. a request-scoped session factory no
        standalone loader could reach): warm reads resolve via the lock-free
        peek without suspending the caller (the await completes immediately);
        on a miss, ONE caller's filler runs on this event loop and every
        concurrent cold caller on the loop awaits that shared fill.

        Because whichever caller arrives first supplies the filler that
        actually runs, all callers' fillers must build the same value —
        differing only in the call-site context they carry. The filler
        follows the loader contract: return a complete, ready-to-share value
        or raise (nothing is published on a raise, so the next call
        retries), and never return None. It runs ON the event loop, so it
        should await network-style I/O; blocking file I/O or heavy parsing
        belongs in a loader reached through aget() instead.

        :param filler: Async callable that builds the value.
        :return: The cached or freshly filled value. Filler exceptions
                propagate to every caller awaiting that fill, and the next
                call starts a fresh attempt.
        """
        value: CachedValue | None = self.peek()
        if value is not None:
            return value

        return await self._await_shared_load(lambda: self._fill_and_publish(filler))

    async def _await_shared_load(self, start_load: Callable[[], Awaitable[CachedValue]]) -> CachedValue:
        """
        The per-event-loop once-gate shared by aget() and aget_or_fill():
        adopt this loop's in-flight load task if one is pending, otherwise
        start a new one from start_load.

        :param start_load: Zero-arg callable producing the awaitable that
                performs the load; only invoked when a new task is needed,
                so no coroutine is created (and left unawaited) on the
                adopt path.
        :return: The loaded value, once the shared task completes.
        """
        loop = get_running_loop()
        task: Task | None = self._loads_in_flight.get(loop)
        if task is None or task.done():
            # A done task is a finished earlier attempt (possibly failed or
            # stale); start a new one. Awaiters of the old task are unaffected.
            task = loop.create_task(start_load())
            self._loads_in_flight[loop] = task
            task.add_done_callback(self._forget_in_flight_load)
        # shield() detaches awaiter cancellation from the shared task: a
        # cancelled awaiter still gets its CancelledError, but the load keeps
        # running and completes for the other awaiters. An unshielded await
        # here would let one cancelled caller cancel everyone else's load,
        # because Task.cancel() propagates into whatever the task is awaiting.
        return await shield(task)

    async def _fill_and_publish(self, filler: Callable[[], Awaitable[CachedValue]]) -> CachedValue:
        """
        Body of an aget_or_fill() once-gate task: get()'s miss discipline,
        restated for a build that happens on the event loop.

        The fingerprint is probed once per miss — serving both as the
        double-check against a fill that completed while this task was being
        scheduled and as the freshness capture published with the value —
        and it is captured BEFORE the filler runs, so a source change
        mid-fill leaves the published entry already stale rather than a torn
        read living forever. Unlike get(), the build runs outside the lock
        (a threading.Lock cannot be held across an await), so the
        double-check is advisory across loops/threads; see the class
        docstring for why that race is benign.
        """
        current_fingerprint: Any = self._fingerprint() if self._fingerprint is not None else None
        entry: tuple[CachedValue, Any] | None = self._entry
        if entry is not None and (self._fingerprint is None or entry[1] == current_fingerprint):
            return entry[0]

        value: CachedValue = await filler()
        # Publish only after the filler fully succeeded, under the lock so
        # the swap serializes with get()'s publish and clear_for_testing().
        with self._lock:
            self._entry = (value, current_fingerprint)
        return value

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
