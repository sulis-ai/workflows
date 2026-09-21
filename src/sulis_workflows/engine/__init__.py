"""The v1 process-definition format's execution engine (WP-02).

Built independently of either DAG-compiler path in ``compiler/`` — see
``docs/work-packages/WP-02-execution-engine.md``, "Why this shape", for
why. No ``sulis.`` import, no vendor SDK, no LangGraph: `engine/run.py`'s
own module docstring is normative on how state and resume actually work
(replaying durable attempt records, not a compiled graph or a
checkpointer). This package follows the same domain-boundary rule
``definition/`` does (WP-01 A5).
"""

from __future__ import annotations
