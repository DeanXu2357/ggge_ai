from __future__ import annotations

import pytest

from tests.ggge_ai_2.unit.mapparser.tolerance import TALLIES, describe


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    tallies = config.stash.get(TALLIES, {})
    if not tallies:
        return
    terminalreporter.section("map parser recognition against the ruled cases")
    for capability, tally in tallies.items():
        terminalreporter.write_line(describe(capability, tally))
