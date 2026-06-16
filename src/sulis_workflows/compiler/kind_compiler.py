"""Kind compiler — typed :class:`KindSpec` → runnable sub-graph (WP-3).

The compiler is the heart of the slice-1 substrate. It takes a parsed
:class:`~sulis_workflows.domain.kind_spec.KindSpec` (produced by
WP-1's parser) and produces a :class:`CompiledKind` whose ``subgraph``
field is a :class:`~sulis_workflows.compiler.graph_dsl.GraphDefinition`
that the existing :class:`~sulis_workflows.compiler.graph_compiler.GenericGraphCompiler`
can execute without modification.

Architectural placement (ADR-200)
---------------------------------

The compiler sits in the workflow service's domain core, alongside
the existing compiler family. It imports only from:

- ``sulis_workflows.domain.*`` — typed Kind spec, engine cache,
  signing, registry, identity, parser.
- ``sulis_workflows.compiler.graph_dsl`` — the existing
  :class:`GraphDefinition` shape (no executor changes required).

It MUST NOT import from content service, task service, or any adapter
module. Lint rules L1 / L2 enforce this.

Two surfaces
------------

* :meth:`KindCompiler.resolve` — consult the studio registry, load the
  Kind via the :class:`KindLoader`, parse the YAML via
  :class:`KindYamlParser`, return the typed :class:`KindSpec`.
* :meth:`KindCompiler.compile` — apply platform-level caps, refuse
  blocking-NFR overrides, build the slice-1 sub-graph, attach the
  per-invocation :class:`EngineCache`, and wire the
  :class:`VerdictSigner` at the (slice-3-stubbed) evaluate boundary.

Platform-level caps (TDD §4.9, MUC-04)
--------------------------------------

The compiler enforces caps independent of the Kind YAML's declarations:

================================================  ============
Cap                                               Default
================================================  ============
``spec.max_iterations``                           10
``spec.decide.five_whys_iterations``              5
``spec.find.context_budget.tokens`` (blocking)    8000
================================================  ============

A Kind YAML requesting a value above the cap is **clamped** and a
:class:`KindIterationCapExceededEvent` is emitted to the configured
:class:`CompilerEventSink`. ``spec.nfr_overrides`` is permitted for
advisory NFRs only; an attempt to override a blocking NFR raises
:class:`OverrideRefused` at compile time.

Cache scope (ADR-204)
---------------------

Every :meth:`compile` call constructs a fresh :class:`EngineCache` and
attaches it to the returned :class:`CompiledKind`. The cache is
one-Kind-invocation scope — never reused across invocations, never
shared between tenants. Cache leakage across tenants is structurally
impossible because a different :class:`InvocationContext` produces a
different cache instance.

Slice-1 sub-graph shape
-----------------------

For a Kind that declares only ``spec.find`` the sub-graph is::

    [find] → END

The find node is a ``function`` node holding a slice-1 sentinel
callable that returns ``{"find_completed": True}``. Slice 2 / 3 / 4
graduate generate / evaluate / decide; the compiler's
:meth:`_build_subgraph` path expands to cover those stages at that
time. A Kind YAML declaring ``generate`` / ``evaluate`` / ``decide`` at
slice 1 currently *parses* but compile raises
:class:`NotYetImplementedInSlice`.

ChainKind (KV-02)
-----------------

``kind: ChainKind`` parses cleanly via WP-1 (the parser does not
discriminate). The compiler refuses to compile ChainKind at slice 1 —
:class:`NotYetImplementedInSlice` is raised with ``stage="ChainKind"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sulis_workflows.compiler.graph_dsl import (
    GraphDefinition,
    NodeDef,
    StateFieldDef,
    StateSchema,
)
from sulis_workflows.domain.context import InvocationContext
from sulis_workflows.domain.engine_cache import (
    CacheEventSink,
    EngineCache,
)
from sulis_workflows.domain.kind_spec import KindSpec, KindSpecBody
from sulis_workflows.domain.kind_yaml_parser import KindYamlParser
from sulis_workflows.domain.registry.kind_resolver import (
    KindLoader,
    KindRef,
    UnknownKindRef,
)
from sulis_workflows.domain.registry.studio_registry import StudioRegistry
from sulis_workflows.domain.signing import VerdictSigner

__all__ = [
    "ClampedCaps",
    "CompiledKind",
    "CompilerEvent",
    "CompilerEventSink",
    "InMemoryCompilerEventSink",
    "KindCompiler",
    "KindIterationCapExceededEvent",
    "NotYetImplementedInSlice",
    "OverrideRefused",
    "PLATFORM_CAP_FIVE_WHYS_ITERATIONS",
    "PLATFORM_CAP_MAX_ITERATIONS",
    "PLATFORM_CAP_FIND_CONTEXT_BUDGET_TOKENS",
]


# ---------------------------------------------------------------------------
# Platform-level hard caps (TDD §4.9 — MUC-04)
# ---------------------------------------------------------------------------
#
# These are the engine-enforced caps. A Kind YAML may declare a smaller
# value (which the compiler honours verbatim) but a larger value is
# clamped at compile time. Blocking NFRs (NFR-9 context budget) are
# additionally not overridable via ``spec.nfr_overrides``.

PLATFORM_CAP_MAX_ITERATIONS: int = 10
PLATFORM_CAP_FIVE_WHYS_ITERATIONS: int = 5
PLATFORM_CAP_FIND_CONTEXT_BUDGET_TOKENS: int = 8000

# Identifiers used in compiler events. Stable strings so downstream
# observability consumers can filter without a Python import.
_EVENT_TYPE_CAP_EXCEEDED = "kind_iteration_cap_exceeded"

# ``spec.nfr_overrides`` keys that the compiler refuses to honour. The
# blocking NFRs are codified in TDD §4.9. Any future blocking NFR must
# be added here too.
_BLOCKING_NFR_KEYS: frozenset[str] = frozenset({"NFR-9"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NotYetImplementedInSlice(Exception):
    """A KindSpec declares a stage / kind not implemented in this slice.

    Slice 1 implements only ``find``. ``generate`` / ``evaluate`` /
    ``decide`` parse cleanly but compile refuses them. ``kind:
    ChainKind`` likewise parses (WP-1) and compile refuses.

    Attributes:
        stage: A human-readable label for the unsupported surface
            (``"generate"``, ``"evaluate"``, ``"decide"``, ``"ChainKind"``).
    """

    def __init__(self, *, stage: str) -> None:
        self.stage = stage
        super().__init__(
            f"{stage!r} is not implemented in slice 1; see KIND_SCHEMA.md and the slice roadmap"
        )


class OverrideRefused(Exception):
    """``spec.nfr_overrides`` attempted to relax a blocking NFR.

    Blocking NFRs (currently NFR-9 — context budget) are enforced
    independent of any Kind YAML declaration. The override is rejected
    at compile time; the Kind never runs.

    Attributes:
        nfr_id: The NFR identifier that the override targeted.
    """

    def __init__(self, *, nfr_id: str) -> None:
        self.nfr_id = nfr_id
        super().__init__(
            f"NFR override refused for {nfr_id!r}: this NFR is blocking "
            f"and cannot be overridden via spec.nfr_overrides"
        )


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClampedCaps:
    """Platform-enforced cap values after clamping the YAML's request.

    Carries both the enforced (post-clamp) values and the originally
    requested values so observability consumers can see whether
    clamping occurred without recomputing.

    Attributes:
        max_iterations:
            Enforced value of ``spec.max_iterations`` (clamped to
            ``PLATFORM_CAP_MAX_ITERATIONS``).
        max_iterations_requested:
            The value declared in the YAML (pre-clamp). ``None`` when
            the YAML did not declare a value.
        five_whys_iterations:
            Enforced value of ``spec.decide.five_whys_iterations``.
        five_whys_iterations_requested:
            Pre-clamp value or ``None``.
        find_context_budget_tokens:
            Enforced value of ``spec.find.context_budget.tokens``.
        find_context_budget_tokens_requested:
            Pre-clamp value or ``None``.
    """

    max_iterations: int
    max_iterations_requested: int | None
    five_whys_iterations: int
    five_whys_iterations_requested: int | None
    find_context_budget_tokens: int
    find_context_budget_tokens_requested: int | None


@dataclass(frozen=True)
class CompiledKind:
    """A sub-graph ready to be executed by the existing graph executor.

    Attributes:
        api_version: The Kind's ``apiVersion`` (mirrors the input spec).
        kind: The Kind's ``kind`` field.
        metadata_version: The Kind's ``metadata.version``.
        run_id: The :class:`InvocationContext`'s ``run_id`` (NFR-11).
            Captured at compile time so downstream stage primitives can
            tag emitted events with the binding run.
        subgraph:
            A :class:`GraphDefinition` the existing
            :class:`GenericGraphCompiler` accepts without modification.
        clamped_caps:
            The post-clamp cap values applied by the compiler.
        engine_cache:
            The per-invocation :class:`EngineCache` (ADR-204). Held on
            the compiled artefact so the execution path threads it into
            every stage-primitive call.
        verdict_signer:
            The :class:`VerdictSigner` wired at the (slice-3-stubbed)
            evaluate boundary. The slice-1 sub-graph contains the
            wiring point; slice 3 fills in the evaluate stage.
    """

    api_version: str
    kind: str
    metadata_version: str
    run_id: str
    subgraph: GraphDefinition
    clamped_caps: ClampedCaps
    engine_cache: EngineCache
    verdict_signer: VerdictSigner


# ---------------------------------------------------------------------------
# Compiler events
# ---------------------------------------------------------------------------


class CompilerEvent(Protocol):
    """Event emitted by the compiler.

    Each concrete event class declares ``event_type`` as a stable
    string (e.g., ``"kind_iteration_cap_exceeded"``). The
    :class:`CompilerEventSink` consumer filters on this attribute.
    Read-only by contract — concrete events are frozen dataclasses.
    """

    @property
    def event_type(self) -> str: ...


@dataclass(frozen=True)
class KindIterationCapExceededEvent:
    """Emitted when a Kind YAML declared a value above a platform cap.

    Carries the offending field path, the YAML's requested value, and
    the enforced (clamped) value. Operators correlate these against
    methodology-change PRs.
    """

    event_type: str
    field: str
    requested: int
    enforced: int
    api_version: str
    kind: str
    metadata_name: str
    metadata_version: str


class CompilerEventSink(Protocol):
    """Sink contract for :class:`CompilerEvent`.

    Implementations MUST be fire-and-forget — they MUST NOT raise on
    emit failure. The compiler relies on the compiled artefact, not
    on the audit emission.
    """

    def emit(self, event: CompilerEvent) -> None: ...


class InMemoryCompilerEventSink:
    """In-memory sink for tests and composition-root local development.

    Accumulates events in an ordered list. Production sinks publish
    to the observability port (WP-8).
    """

    def __init__(self) -> None:
        self._events: list[CompilerEvent] = []

    def emit(self, event: CompilerEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[CompilerEvent]:
        """Read-only view of accumulated events (caller must not mutate)."""
        return list(self._events)


class _NullCompilerEventSink:
    """No-op sink — used when no event_sink is supplied at construction."""

    def emit(self, event: CompilerEvent) -> None:  # pragma: no cover - trivial
        return None


# ---------------------------------------------------------------------------
# Slice-1 find node
# ---------------------------------------------------------------------------


async def _slice_1_find_stage(state: dict[str, Any]) -> dict[str, Any]:
    """Slice-1 sentinel for the find stage.

    The full find stage lands with the stage primitives + execution
    path (WP-5, WP-6, WP-7, WP-9). At slice 1 the compiler emits a
    sub-graph the existing executor can run end-to-end so the WPs
    downstream of WP-3 (WP-9, WP-10, WP-KIND-HANDLER) have a concrete
    artefact to consume. The find node returns one tagged state-channel
    write so the integration test can assert the node ran.
    """
    return {"find_completed": True}


# ---------------------------------------------------------------------------
# The compiler
# ---------------------------------------------------------------------------


class KindCompiler:
    """Compile a parsed :class:`KindSpec` into a runnable sub-graph.

    Constructed once at the composition root; called per Kind
    invocation. Stateless beyond the injected dependencies — every
    :meth:`compile` call produces a fresh :class:`EngineCache`.

    Parameters
    ----------
    studio_registry:
        The :class:`StudioRegistry` allowlist (WP-ARMOR-03 / ADR-208).
        :meth:`resolve` consults this before invoking the loader so an
        unregistered ``apiVersion`` is refused with :class:`UnknownStudio`.
    kind_loader:
        The :class:`KindLoader` boundary that turns ``(apiVersion,
        kind, platform_id)`` into bytes. Missing returns ``None`` →
        :class:`UnknownKindRef`.
    yaml_parser:
        :class:`KindYamlParser`. Tests can inject a custom parser; in
        production the composition root passes the standard one.
    verdict_signer:
        :class:`VerdictSigner` wired at the evaluate boundary. The
        slice-1 sub-graph carries the wiring point; slice 3 fills in
        the evaluate stage that consumes it.
    cache_event_sink:
        Optional :class:`CacheEventSink`. Forwarded to the per-
        invocation :class:`EngineCache`. Production wires to the
        observability port (WP-8); tests use
        :class:`InMemoryCacheEventSink`.
    compile_event_sink:
        Optional :class:`CompilerEventSink`. Receives
        :class:`KindIterationCapExceededEvent` on cap clamping.
    """

    def __init__(
        self,
        *,
        studio_registry: StudioRegistry,
        kind_loader: KindLoader,
        yaml_parser: KindYamlParser,
        verdict_signer: VerdictSigner,
        cache_event_sink: CacheEventSink | None = None,
        compile_event_sink: CompilerEventSink | None = None,
    ) -> None:
        self._registry = studio_registry
        self._loader = kind_loader
        self._parser = yaml_parser
        self._verdict_signer = verdict_signer
        self._cache_event_sink = cache_event_sink
        self._compile_event_sink: CompilerEventSink = compile_event_sink or _NullCompilerEventSink()

    # ----------------------------------------------------------------------
    # resolve()
    # ----------------------------------------------------------------------

    async def resolve(
        self,
        api_version: str,
        kind: str,
        *,
        metadata_version: str | None,
        ctx: InvocationContext,
    ) -> KindSpec:
        """Resolve a Kind reference to a typed :class:`KindSpec`.

        Three steps:

        1. Studio registry lookup. ``apiVersion`` not registered →
           :class:`UnknownStudio`.
        2. Loader fetch keyed on ``(apiVersion, kind, platform_id)``.
           Missing → :class:`UnknownKindRef`.
        3. Parse via :class:`KindYamlParser`. Parse errors propagate
           verbatim — the parser's error types are part of the public
           surface.

        Parameters
        ----------
        api_version:
            Kind's ``apiVersion``.
        kind:
            Kind's ``kind`` field (no suffix; KIND_SCHEMA KV-02).
        metadata_version:
            Optional declared version. Not used for selection at slice 1
            (the loader keys on apiVersion + kind), but recorded for
            future maturity where multiple versions of the same Kind
            may coexist. Passed through unchanged to the parsed spec.
        ctx:
            The :class:`InvocationContext` carrying ``platform_id``.

        Raises
        ------
        UnknownStudio
            ``api_version`` is not in the studio registry.
        UnknownKindRef
            The loader returned ``None`` for the caller's tenant.
        """
        # Step 1: registry — raises UnknownStudio on miss.
        self._registry.resolve_studio(api_version)

        # Step 2: loader.
        kind_ref = KindRef(api_version=api_version, kind=kind)
        record = self._loader.load(kind_ref, platform_id=ctx.platform_id)
        if record is None:
            raise UnknownKindRef(kind_ref, platform_id=ctx.platform_id)

        # Step 3: parse.
        yaml_text = record.yaml_bytes.decode("utf-8")
        return await self._parser.parse(yaml_text, source_path=record.metadata_name)

    # ----------------------------------------------------------------------
    # compile()
    # ----------------------------------------------------------------------

    async def compile(self, spec: KindSpec, *, cache_ctx: InvocationContext) -> CompiledKind:
        """Compile a :class:`KindSpec` into a :class:`CompiledKind`.

        Steps (in order):

        1. Refuse ChainKind — slice 1 does not implement it.
        2. Refuse non-find stages — slice 1 implements only find.
        3. Refuse blocking-NFR overrides.
        4. Clamp platform-level caps; emit clamp events.
        5. Build the slice-1 sub-graph (one ``find`` node).
        6. Construct a fresh :class:`EngineCache` (ADR-204).
        7. Return :class:`CompiledKind`.

        Parameters
        ----------
        spec:
            Parsed Kind specification (from :meth:`resolve` or the
            parser directly).
        cache_ctx:
            The :class:`InvocationContext` whose ``run_id`` is captured
            on the compiled artefact (NFR-11 propagation).

        Raises
        ------
        NotYetImplementedInSlice
            The spec declares ChainKind or a non-find stage.
        OverrideRefused
            The spec declares ``spec.nfr_overrides`` for a blocking NFR.
        """
        # 1. ChainKind: parses but does not compile (KIND_SCHEMA KV-02).
        if spec.kind == "ChainKind":
            raise NotYetImplementedInSlice(stage="ChainKind")

        # 2. Non-find stages: refused in slice 1. The body keeps the
        #    decide block for cap-clamping (five_whys_iterations) but
        #    the *sub-graph* only contains find.
        self._guard_slice_1_stages(spec.spec)

        # 3. NFR-overrides on blocking NFRs are refused.
        self._guard_nfr_overrides(spec.spec.nfr_overrides)

        # 4. Platform-level cap clamping.
        clamped = self._clamp_platform_caps(spec)

        # 5. Build the sub-graph.
        subgraph = self._build_subgraph(spec)

        # 6. Fresh engine cache per invocation (ADR-204 invariant).
        engine_cache = EngineCache(event_sink=self._cache_event_sink)

        # 7. Return the compiled artefact.
        return CompiledKind(
            api_version=spec.api_version,
            kind=spec.kind,
            metadata_version=spec.metadata.version,
            run_id=cache_ctx.run_id,
            subgraph=subgraph,
            clamped_caps=clamped,
            engine_cache=engine_cache,
            verdict_signer=self._verdict_signer,
        )

    # ------------------------------------------------------------------
    # Compile-time helpers
    # ------------------------------------------------------------------

    def _guard_slice_1_stages(self, body: KindSpecBody) -> None:
        """Refuse generate / evaluate / decide-as-execution at slice 1.

        ``spec.decide`` *parses* in slice 1 — the parser accepts it so
        cap-clamping can read ``five_whys_iterations`` — but the
        sub-graph contains no decide node. Likewise generate and
        evaluate parse but do not execute. A Kind YAML that exercises
        these stages is refused at compile.

        Slice-1 rule: a spec carrying ``generate`` or ``evaluate``
        raises. ``decide`` is permitted because its only slice-1
        purpose is cap-clamping; the compiler does not emit a decide
        node.
        """
        if body.generate is not None:
            raise NotYetImplementedInSlice(stage="generate")
        if body.evaluate is not None:
            raise NotYetImplementedInSlice(stage="evaluate")

    def _guard_nfr_overrides(self, overrides: dict[str, Any] | None) -> None:
        """Refuse overrides targeting blocking NFRs.

        ``spec.nfr_overrides`` is permitted for advisory NFRs; the
        compiler does not consume them at slice 1 (the execution path
        does, in slice 3+). Blocking NFRs (currently NFR-9 context
        budget) are enforced at the engine boundary regardless of any
        override; an attempt to relax them raises.
        """
        if not overrides:
            return
        for key in overrides.keys():
            if key in _BLOCKING_NFR_KEYS:
                raise OverrideRefused(nfr_id=key)

    def _clamp_platform_caps(self, spec: KindSpec) -> ClampedCaps:
        """Apply platform-level caps to the spec's declared values.

        Three caps are checked:

        * ``spec.max_iterations`` → :data:`PLATFORM_CAP_MAX_ITERATIONS`
        * ``spec.decide.five_whys_iterations`` →
          :data:`PLATFORM_CAP_FIVE_WHYS_ITERATIONS`
        * ``spec.find.context_budget.tokens`` →
          :data:`PLATFORM_CAP_FIND_CONTEXT_BUDGET_TOKENS`

        A YAML-declared value above any cap is clamped to the cap and
        a :class:`KindIterationCapExceededEvent` is emitted. The
        ClampedCaps record carries both the enforced and the requested
        value so consumers can audit without re-reading the spec.
        """
        body = spec.spec

        # max_iterations
        requested_max_iter = body.max_iterations
        enforced_max_iter = self._clamp_one(
            requested=requested_max_iter,
            cap=PLATFORM_CAP_MAX_ITERATIONS,
            field="spec.max_iterations",
            spec=spec,
        )

        # decide.five_whys_iterations
        requested_five_whys: int | None = None
        if body.decide is not None:
            requested_five_whys = body.decide.five_whys_iterations
        enforced_five_whys = self._clamp_one(
            requested=requested_five_whys,
            cap=PLATFORM_CAP_FIVE_WHYS_ITERATIONS,
            field="spec.decide.five_whys_iterations",
            spec=spec,
        )

        # find.context_budget.tokens (blocking NFR-9 floor)
        requested_tokens = self._extract_context_budget_tokens(body)
        enforced_tokens = self._clamp_one(
            requested=requested_tokens,
            cap=PLATFORM_CAP_FIND_CONTEXT_BUDGET_TOKENS,
            field="spec.find.context_budget.tokens",
            spec=spec,
        )

        return ClampedCaps(
            max_iterations=enforced_max_iter,
            max_iterations_requested=requested_max_iter,
            five_whys_iterations=enforced_five_whys,
            five_whys_iterations_requested=requested_five_whys,
            find_context_budget_tokens=enforced_tokens,
            find_context_budget_tokens_requested=requested_tokens,
        )

    def _clamp_one(
        self,
        *,
        requested: int | None,
        cap: int,
        field: str,
        spec: KindSpec,
    ) -> int:
        """Clamp one cap. Emit the clamp event when applicable.

        Returns the enforced (post-clamp) value. When ``requested`` is
        ``None`` the cap is the enforced value (no clamping occurred,
        no event emitted). When ``requested`` is at or below the cap,
        the requested value is the enforced value (no event emitted).
        Only an over-cap declaration produces an event.
        """
        if requested is None:
            return cap
        if requested <= cap:
            return requested
        self._compile_event_sink.emit(
            KindIterationCapExceededEvent(
                event_type=_EVENT_TYPE_CAP_EXCEEDED,
                field=field,
                requested=requested,
                enforced=cap,
                api_version=spec.api_version,
                kind=spec.kind,
                metadata_name=spec.metadata.name,
                metadata_version=spec.metadata.version,
            )
        )
        return cap

    @staticmethod
    def _extract_context_budget_tokens(body: KindSpecBody) -> int | None:
        """Read ``spec.find.context_budget.tokens`` if present.

        The parser stores ``context_budget`` as a plain dict (it is a
        slice-1 ``warned``-tier field whose shape may evolve). This
        helper inspects the dict defensively — a missing key, wrong
        type, or absent ``find`` returns ``None``, which the cap-clamping
        path treats as "no override declared".
        """
        if body.find is None:
            return None
        budget = body.find.context_budget
        if not isinstance(budget, dict):
            return None
        tokens = budget.get("tokens")
        if isinstance(tokens, int):
            return tokens
        return None

    # ------------------------------------------------------------------
    # Sub-graph builder
    # ------------------------------------------------------------------

    def _build_subgraph(self, spec: KindSpec) -> GraphDefinition:
        """Build the slice-1 sub-graph for ``spec``.

        The sub-graph carries exactly one node — ``find`` — wired to
        ``END`` via the implicit terminal-leaf detection of the
        existing :class:`GenericGraphCompiler`. Slice 2 / 3 / 4
        extend this with generate / evaluate / decide.

        The state schema declares one channel — ``find_completed``  —
        so the integration test can assert the node ran end-to-end.
        Production stage primitives will write richer state channels
        (artifact paths, observability tags); the slice-1 channel set
        is the minimum the sub-graph needs to round-trip.
        """
        # Slice 1 emits a single-node sub-graph. The existing
        # GenericGraphCompiler auto-wires terminal leaves to END so no
        # explicit edges are needed; ``terminal_nodes=["find"]``
        # surfaces the leaf to that auto-wiring path. Slice 2+ extends
        # the edge list when generate / evaluate / decide land.
        return GraphDefinition(
            name=f"kind:{spec.api_version}#{spec.kind}",
            nodes=[
                NodeDef(
                    id="find",
                    type="function",
                    handler=_slice_1_find_stage,
                )
            ],
            edges=[],
            state_schema=StateSchema(
                fields=[StateFieldDef(name="find_completed", type_hint="bool", default=False)]
            ),
            entry_point="find",
            terminal_nodes=["find"],
        )
