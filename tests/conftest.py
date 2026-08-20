"""Shared fixtures. The engine executable is built once for the whole session."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1] / "engine"


@pytest.fixture(scope="session")
def engine_executable(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("go") is None:
        pytest.skip("go is not on PATH")
    target = tmp_path_factory.mktemp("engine") / "battle-engine"
    subprocess.run(["go", "build", "-o", str(target), "."], cwd=ENGINE_DIR, check=True)
    return target
