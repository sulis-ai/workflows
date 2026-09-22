"""sulis-workflows — the Sulis workflow engine (shared library).

Compiles canonical Workflow entities into a LangGraph graph and executes it under
injected adapters. The same library runs server-side or client-side (DR-040).

    from sulis_workflows import compiler, domain
"""

from __future__ import annotations

__version__ = "0.13.0"
__all__ = ["__version__"]
