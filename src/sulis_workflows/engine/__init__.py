"""The v1 process-definition format's execution engine (WP-02).

Targets LangGraph directly rather than extending either DAG-compiler path
in ``compiler/`` — see ``docs/work-packages/WP-02-execution-engine.md``,
"Why this shape", for why. No ``sulis.`` import, no vendor SDK: this
package follows the same domain-boundary rule ``definition/`` does
(WP-01 A5).
"""

from __future__ import annotations
