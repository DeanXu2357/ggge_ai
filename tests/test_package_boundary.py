"""新包自足：批 0 的模組不得 import 任何舊包（docs/module-map.md 舊碼處置）。"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "ggge_ai"
NEW_MODULES = ("contracts.py", "stage", "sandbox", "runtime")
FROZEN = {
    "domain",
    "vision",
    "battle",
}


def _new_files() -> list[Path]:
    files: list[Path] = []
    for entry in NEW_MODULES:
        target = PACKAGE_ROOT / entry
        files.extend([target] if target.is_file() else sorted(target.rglob("*.py")))
    return files


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = path.relative_to(PACKAGE_ROOT.parent).with_suffix("").parts[:-1]
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                modules.append(node.module or "")
            else:
                base = package[: len(package) - (node.level - 1)]
                modules.append(".".join([*base, node.module or ""]).rstrip("."))
    return modules


def test_the_new_package_files_are_all_present():
    names = {path.relative_to(PACKAGE_ROOT).as_posix() for path in _new_files()}

    assert "sandbox/advise.py" in names
    assert "runtime/journal.py" in names


def test_no_new_module_imports_a_frozen_package():
    offenders = []
    for path in _new_files():
        for module in _imported_modules(path):
            parts = module.split(".")
            if parts[0] == "ggge_ai" and len(parts) > 1 and parts[1] in FROZEN:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)} -> {module}")

    assert offenders == []
