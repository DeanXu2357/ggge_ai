"""Crawl the soshage datamine into data/datamine/<version-stamp>/.

    uv run python scripts/crawl_datamine.py [--out DIR] [--base-url URL]

The store is a drift signal, not an authority. The screen stays the authority
for every live decision (docs/reference/datamine-source.md).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATAMINE_DIR = PROJECT_ROOT / "data" / "datamine"

BASE_URL = "https://soshage.com"
VERSION_PATH = "/ggetapi/version"
FORMULA_PATH = "/gget/formula"
TABLE_PATHS = {
    "unit": "/ggetapi/en/unit",
    "weapon": "/ggetapi/en/weapon",
    "stage": "/ggetapi/en/stage",
}
USER_AGENT = "ggge_ai-datamine-crawler/1 (+https://github.com/DeanXu2357/ggge_ai)"

Fetch = Callable[[str], bytes]

_DIV = re.compile(r"<(/?)div\b")
_CODE = re.compile(r"<code\b[^>]*>(.*?)</code>", re.S)
_TAG = re.compile(r"<[^>]+>")


def _text(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", markup))).strip()


def _tab_panel(page: str, value: str) -> str:
    """Cut out the tab panel of the calculator page.

    The tab trigger carries the same 'data-value' as its panel, so the search
    also asks for the 'tabs-content' slot, and it asks that the marker sits in
    the opening tag itself.
    """
    marker = f'data-value="{value}"'
    at = page.find(marker)
    while at >= 0:
        start = page.rindex("<", 0, at)
        if page.startswith("<div", start) and 'data-slot="tabs-content"' in page[start:at]:
            depth = 0
            for match in _DIV.finditer(page, start):
                depth += -1 if match.group(1) else 1
                if depth == 0:
                    return page[start : page.index(">", match.end()) + 1]
            break
        at = page.find(marker, at + 1)
    raise ValueError(f"the page holds no tab panel {value!r}")


def formula_chain(page: str) -> dict:
    """Read the formula tab of the calculator page.

    The page is not byte stable: it also carries prefetched API blobs, and the
    server emits those in completion order. The tab itself is static markup.
    """
    panel = _tab_panel(page, "formula")
    lines = [_text(match.group(1)) for match in _CODE.finditer(panel)]
    notes = [note for note in (_text(part) for part in _TAG.split(_CODE.sub("", panel))) if note]
    if not lines:
        raise ValueError("the formula tab holds no formula line")
    return {"lines": lines, "notes": notes}


def _row_counts(name: str, payload) -> dict[str, int]:
    if isinstance(payload, list):
        return {name: len(payload)}
    return {key: len(value) for key, value in payload.items() if isinstance(value, list | dict)}


def _dump(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def crawl(fetch: Fetch, out_root: Path) -> Path:
    version = json.loads(fetch(VERSION_PATH))["version"]
    payloads = {name: json.loads(fetch(path)) for name, path in TABLE_PATHS.items()}
    payloads["formula"] = formula_chain(fetch(FORMULA_PATH).decode("utf-8"))
    paths = {**TABLE_PATHS, "formula": FORMULA_PATH}

    out_dir = out_root / str(version)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, payload in payloads.items():
        blob = _dump(payload)
        (out_dir / f"{name}.json").write_bytes(blob)
        files[f"{name}.json"] = {
            "path": paths[name],
            "kind": "extracted" if name == "formula" else "json",
            "rows": _row_counts(name, payload),
            "bytes": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
        }

    (out_dir / "manifest.json").write_bytes(
        _dump({"version": version, "files": files, "source": BASE_URL})
    )
    return out_dir


class HttpFetch:
    def __init__(self, base_url: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def __call__(self, path: str) -> bytes:
        request = urllib.request.Request(self._base_url + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DATAMINE_DIR)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out_dir = crawl(HttpFetch(args.base_url, args.timeout), args.out)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"started {started}")
    print(f"version {manifest['version']}")
    for name, entry in sorted(manifest["files"].items()):
        print(f"  {name}: {entry['rows']} {entry['bytes']} bytes")
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
