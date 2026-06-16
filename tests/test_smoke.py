"""Smoke test — the package imports + langgraph is available.

Replaced by real compiler/engine tests at v0.1.0 (compile-a-graph standalone).
"""

from __future__ import annotations


def test_package_imports():
    import sulis_workflows
    from sulis_workflows import compiler, domain  # noqa: F401
    from sulis_workflows.domain import ports  # noqa: F401

    assert sulis_workflows.__version__ == "0.3.0"


def test_langgraph_available():
    # The engine's one substantive runtime dep — proves the env is set up.
    from langgraph.graph import StateGraph  # noqa: F401
