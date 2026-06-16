"""Vendored no-op tracing — the `span_context` default.

The platform's `observability.tracing.span_context` is a tracing helper. In the
shared engine library it defaults to a **no-op**, so the engine carries no platform
tracing dependency; a consumer adds real tracing via the `ObservabilityPort`. Per DR-040
(the engine is a library; observability is an injected adapter, not a hard import).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class _NoopSpan:
    """Absorbs any span call (`set_attribute`, `add_event`, `set_status`, …) as a no-op,
    so engine code written for a real tracing span runs unchanged with tracing disabled."""

    def __getattr__(self, _name):
        def _noop(*args, **kwargs):
            return None
        return _noop


@contextmanager
def span_context(*args, **kwargs) -> Iterator[_NoopSpan]:
    """No-op span context. Accepts any args (name, attributes, …); yields a no-op span."""
    yield _NoopSpan()
