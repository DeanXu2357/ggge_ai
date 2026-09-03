"""Load a datamine dump into the game data store.

    uv run python scripts/ingest_datamine.py [DUMP_DIR] [--database-url URL]

The dump keeps its own version stamp. A second run of the same stamp
replaces its rows; it leaves the rows of every other stamp alone.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ggge_ai.gamedata.normalize import Dump, normalize, raw_rows, read_payload
from ggge_ai.gamedata.store import Store

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATAMINE_DIR = PROJECT_ROOT / "data" / "datamine"


def newest_dump(root: Path) -> Path:
    dumps = sorted(path for path in root.iterdir() if path.is_dir())
    if not dumps:
        raise SystemExit(f"no dump under {root}")
    return dumps[-1]


def read_manifest(dump_dir: Path) -> dict:
    return json.loads((dump_dir / "manifest.json").read_text(encoding="utf-8"))


def ingest(dump_dir: Path, store: Store) -> dict[str, int]:
    manifest = read_manifest(dump_dir)
    stamp = manifest["version"]
    rows = normalize(stamp, Dump.read(dump_dir))
    raw: list[tuple] = []
    for file_name in sorted(manifest["files"]):
        name = file_name.removesuffix(".json")
        raw.extend(raw_rows(stamp, name, read_payload(dump_dir, name)))
    store.write_constants()
    store.write_stamp(rows, raw)
    return store.counts(stamp)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump_dir", type=Path, nargs="?")
    parser.add_argument("--database-url")
    args = parser.parse_args()

    dump_dir = args.dump_dir or newest_dump(DATAMINE_DIR)
    with Store(args.database_url) as store:
        counts = ingest(dump_dir, store)
    print(f"stamp {read_manifest(dump_dir)['version']}")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
