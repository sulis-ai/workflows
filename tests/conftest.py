"""Test-run setup shared by every test."""

from __future__ import annotations

import tempfile

import pytest


def pytest_configure(config: pytest.Config) -> None:
    # pytest keeps its temp folders in /tmp/pytest-of-<user>, and refuses to run any
    # test using ``tmp_path`` when that folder belongs to somebody else (a shared or
    # reused machine). Give the run its own folder in that case, so a test is judged
    # on what it checks and not on who owns /tmp. An explicit --basetemp wins.
    if config.option.basetemp is None:
        config.option.basetemp = tempfile.mkdtemp(prefix="pytest-run-")
