"""One-Kind-invocation-scoped engine cache (WP-4).

Holds read-results (file content, parsed YAML, glob expansions) inside
a single Kind invocation. A fresh :class:`EngineCache` is constructed
per :meth:`KindCompiler.compile` call (WP-3) and discarded when the
invocation ends.

Design (ADR-204)
----------------

* **Scope.** One invocation. Constructed without arguments, populated
  inline, garbage-collected at invocation end. Tenant isolation is
  structural — different invocations are different cache instances.

* **Freshness.** The cache delegates the freshness comparison to a
  :class:`FreshCheck` value object the caller supplies. The cache
  never snoops adapter internals (mtime is a filesystem concept; SHA
  is a remote-API concept). Equality comparison on :class:`FreshCheck`
  decides hit vs miss.

* **Namespaces.** File, YAML, and glob caches share an
  :class:`EngineCache` instance but never collide on key — each is a
  distinct dict keyed by ``(namespace, key)``.

* **Eviction.** None within the invocation. Above the soft capacity
  (default 1000), the cache silently no-ops — fetches still serve the
  caller but results are not stored. Cap is intentionally generous;
  no slice-1 Kind invocation comes near it. Above the cap, behaviour
  is correctness-preserving (every read becomes a fetch), only the
  performance benefit is lost.

* **Instrumentation.** Every read emits a :class:`CacheEvent` carrying
  the namespace, key, and a ``cache_hit`` boolean. Production wires the
  sink to the observability port (WP-8); tests use
  :class:`InMemoryCacheEventSink`.

* **Identity.** A cache hit returns the same Python object the original
  fetch produced (``is``, not ``==``). All cached values are
  treated as immutable by contract.

The contract surface is three coroutine methods —
:meth:`EngineCache.get_or_fetch_file`,
:meth:`EngineCache.get_or_fetch_yaml`,
:meth:`EngineCache.get_or_fetch_glob`. Each returns the value plus a
``cache_hit`` boolean so callers (the compiler, the stage primitives)
can record the signal without re-asking the cache.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

__all__ = [
    "DEFAULT_CACHE_CAPACITY",
    "CacheEvent",
    "CacheEventSink",
    "EngineCache",
    "FileEntry",
    "FreshCheck",
    "InMemoryCacheEventSink",
    "MtimeFreshCheck",
    "ShaFreshCheck",
    "WorkspacePath",
]


# --- Bounds ----------------------------------------------------------------

# Soft capacity. Above this, the cache serves fetches but stores nothing.
# Slice 1's largest expected invocation reads on the order of dozens of
# files, parses a single Kind YAML, and runs at most a handful of globs;
# 1000 is comfortably high. The cap exists as defence-in-depth, not as a
# usage-shaping mechanism.
DEFAULT_CACHE_CAPACITY: int = 1000


# --- Value objects ---------------------------------------------------------


@dataclass(frozen=True)
class WorkspacePath:
    """A workspace-relative or backend-addressed path.

    Held as a thin frozen wrapper around the raw string so the cache's
    keys are hashable value-objects rather than bare strings. Equality
    and hashing flow from the underlying string.
    """

    path: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.path


@dataclass(frozen=True)
class FreshCheck:
    """Base class for freshness checks.

    Concrete subclasses (:class:`MtimeFreshCheck`, :class:`ShaFreshCheck`)
    carry the backend-specific fingerprint. The cache compares
    ``FreshCheck`` instances by equality; mismatch is a miss.

    Two checks of different concrete types never compare equal, even on
    identical scalar contents — the frozen dataclass auto-generates
    equality that includes the type discriminator.
    """


@dataclass(frozen=True)
class MtimeFreshCheck(FreshCheck):
    """Filesystem-backed freshness check.

    Two reads of the same path are fresh-equal iff the path's mtime is
    unchanged. Stored as ``float`` seconds-since-epoch so caller-side
    comparison is exact (no rounding).
    """

    mtime: float


@dataclass(frozen=True)
class ShaFreshCheck(FreshCheck):
    """Remote-backend freshness check.

    GitHub/GitLab/etc. APIs return a content SHA per blob; equality of
    that SHA means the blob's bytes are byte-identical.
    """

    sha: str


@dataclass(frozen=True)
class FileEntry:
    """A cached file read.

    Carries the bytes plus the mtime observed at fetch time. Callers
    that need the freshness fingerprint for downstream caching (e.g.,
    YAML parses keyed against the same file) read it from here.
    """

    path: WorkspacePath
    content: bytes
    mtime: float


# --- Instrumentation -------------------------------------------------------


@dataclass(frozen=True)
class CacheEvent:
    """Emitted on every cache read.

    Carries the ``namespace`` (file / yaml / glob), the ``key`` used for
    lookup (string form for downstream filtering), and the ``cache_hit``
    boolean. The observability adapter (WP-8) consumes these and folds
    them into the stage_primitive_call event stream so cache behaviour
    is visible alongside the read itself.
    """

    namespace: str
    key: str
    cache_hit: bool


class CacheEventSink(Protocol):
    """Sink contract for cache events.

    Implementations MUST NOT raise on :meth:`emit` — the cache does not
    catch sink errors and a raise here would mask the underlying fetch.
    """

    def emit(self, event: CacheEvent) -> None: ...


class InMemoryCacheEventSink:
    """In-memory sink for tests and composition-root local development.

    Accumulates events in an ordered list. Production wires a sink that
    publishes to the observability port (WP-8).
    """

    def __init__(self) -> None:
        self._events: list[CacheEvent] = []

    def emit(self, event: CacheEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[CacheEvent]:
        """Read-only view of accumulated events (caller must not mutate)."""
        return list(self._events)


class _NullCacheEventSink:
    """No-op sink — used when no event_sink is supplied at construction."""

    def emit(self, event: CacheEvent) -> None:  # pragma: no cover - trivial
        return None


# --- The cache itself ------------------------------------------------------


# Internal namespace tags. Strings are kept so :class:`CacheEvent` carries
# a downstream-readable label.
_NS_FILE = "file"
_NS_YAML = "yaml"
_NS_GLOB = "glob"


class EngineCache:
    """One-invocation-scoped read-result cache.

    Constructed fresh per Kind invocation (WP-3 :class:`KindCompiler`
    instantiates one on each :meth:`compile` call). Holds parsed-YAML,
    file-content reads, and glob results so the find stage's second
    access of a path is served from memory.

    Parameters
    ----------
    capacity:
        Soft cap on entries across all three namespaces. Above the cap,
        new reads still serve the caller's fetch but are not stored.
        Defaults to :data:`DEFAULT_CACHE_CAPACITY` (1000) — generous
        enough that slice-1 Kinds will never approach it.
    event_sink:
        Optional :class:`CacheEventSink`. Tests pass
        :class:`InMemoryCacheEventSink`; production passes the
        observability adapter's sink (WP-8). If omitted, events are
        emitted to a null sink.
    """

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CACHE_CAPACITY,
        event_sink: CacheEventSink | None = None,
    ) -> None:
        self._capacity: int = capacity
        self._event_sink: CacheEventSink = event_sink or _NullCacheEventSink()

        # Each namespace is a plain dict. Keys carry the freshness
        # fingerprint so a changed file misses without explicit
        # invalidation — the next read with a new FreshCheck is just a
        # different key.
        #
        # File / YAML namespaces key on (path, fresh_check) — a tuple of
        # value-objects, both hashable.
        # Glob namespace keys on (pattern, root) — globs have no
        # freshness fingerprint at slice 1 (acceptable because globs
        # are re-evaluated only across invocations, and within an
        # invocation the underlying filesystem doesn't change in ways
        # the find stage observes).
        self._file: dict[tuple[WorkspacePath, FreshCheck], FileEntry] = {}
        self._yaml: dict[tuple[WorkspacePath, FreshCheck], Any] = {}
        self._glob: dict[tuple[str, WorkspacePath], list[WorkspacePath]] = {}

    async def get_or_fetch_file(
        self,
        path: WorkspacePath,
        *,
        fresh_check: FreshCheck,
        fetch: Callable[[], Awaitable[FileEntry]],
    ) -> tuple[FileEntry, bool]:
        """Return ``(entry, cache_hit)`` for a file read.

        Cache hit iff ``(path, fresh_check)`` is already present.
        """
        return await self._get_or_fetch(
            store=self._file,
            key=(path, fresh_check),
            namespace=_NS_FILE,
            event_key=str(path),
            fetch=fetch,
        )

    async def get_or_fetch_yaml(
        self,
        path: WorkspacePath,
        *,
        fresh_check: FreshCheck,
        fetch: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, bool]:
        """Return ``(parsed, cache_hit)`` for a YAML read.

        Cache hit iff ``(path, fresh_check)`` is already present. The
        YAML namespace is distinct from the file namespace — caching
        the raw bytes does not pre-populate the YAML cache.
        """
        return await self._get_or_fetch(
            store=self._yaml,
            key=(path, fresh_check),
            namespace=_NS_YAML,
            event_key=str(path),
            fetch=fetch,
        )

    async def get_or_fetch_glob(
        self,
        pattern: str,
        root: WorkspacePath,
        *,
        fetch: Callable[[], Awaitable[list[WorkspacePath]]],
    ) -> tuple[list[WorkspacePath], bool]:
        """Return ``(paths, cache_hit)`` for a glob expansion.

        Cache hit iff ``(pattern, root)`` is already present. Glob
        expansion within a single invocation is re-used aggressively
        because the find stage frequently re-asks for the same pattern.
        """
        return await self._get_or_fetch(
            store=self._glob,
            key=(pattern, root),
            namespace=_NS_GLOB,
            event_key=f"{pattern}@{root}",
            fetch=fetch,
        )

    # --- Internals ---------------------------------------------------------

    async def _get_or_fetch(
        self,
        *,
        store: dict[Any, Any],
        key: Any,
        namespace: str,
        event_key: str,
        fetch: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, bool]:
        """Generic lookup-or-fetch for any namespace.

        Three concerns, in order:

        1. Lookup — hit returns the stored value with ``cache_hit=True``.
        2. Fetch — miss invokes the caller's fetch callable. Exceptions
           propagate without poisoning the cache.
        3. Store + emit — successful fetches are stored if there is
           capacity; every read (hit or miss) emits one
           :class:`CacheEvent`.
        """
        if key in store:
            value = store[key]
            self._emit(namespace, event_key, cache_hit=True)
            return value, True

        value = await fetch()
        self._store(store, key, value)
        self._emit(namespace, event_key, cache_hit=False)
        return value, False

    def _store(self, store: dict[Any, Any], key: Any, value: Any) -> None:
        """Persist a value if we're below capacity; otherwise no-op.

        The no-op-at-capacity policy is intentional — see ADR-204.
        Above the cap, correctness is preserved (every subsequent read
        becomes a fetch), only the performance benefit is lost.
        """
        if self._size() >= self._capacity:
            return
        store[key] = value

    def _size(self) -> int:
        """Total entries across all namespaces."""
        return len(self._file) + len(self._yaml) + len(self._glob)

    def _emit(self, namespace: str, key: str, *, cache_hit: bool) -> None:
        """Emit a :class:`CacheEvent` to the configured sink."""
        self._event_sink.emit(CacheEvent(namespace=namespace, key=key, cache_hit=cache_hit))
