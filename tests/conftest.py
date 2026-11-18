from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-tolerance-baseline",
        action="store_true",
        help="write the current map parser recognition rates into tolerance_baseline.json",
    )
