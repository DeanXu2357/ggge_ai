import ast
from pathlib import Path

NEW_ROOT = Path(__file__).resolve().parents[1] / "src" / "ggge_ai_2"


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.append(node.module or "")
    return names


def test_ggge_ai_2_does_not_import_the_old_package():
    offenders = [
        f"{path.relative_to(NEW_ROOT)} -> {name}"
        for path in sorted(NEW_ROOT.rglob("*.py"))
        for name in _imports(path)
        if name.split(".")[0] == "ggge_ai"
    ]

    assert offenders == []
