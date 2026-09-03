"""Print the engine payload of one holding.

    uv run python scripts/load_holding.py --stamp STAMP --unit ID --level N
        --pilot ID --pilot-level N [--limit-break 0..3] [--mech-sp] [--mech-ssp]
        [--weapon-level 1..5] [--supporter ID --supporter-level N
        --supporter-limit-break 0..3] [--from-dump DIR] [--database-url URL]

The default source is the game data store. With --from-dump the script
reads a datamine dump and needs no database.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from ggge_ai.gamedata.holding import Holding, assemble, payload
from ggge_ai.gamedata.normalize import Dump, normalize
from ggge_ai.gamedata.records import Catalog
from ggge_ai.gamedata.store import Store


@dataclass(frozen=True)
class StampedStore:
    """The store bound to one stamp, in the read shape that 'load' wants."""

    store: Store
    stamp: str

    def unit(self, unit_id: int):
        return self.store.read_unit(self.stamp, unit_id)

    def pilot(self, pilot_id: int):
        return self.store.read_pilot(self.stamp, pilot_id)

    def supporter(self, supporter_id: int):
        return self.store.read_supporter(self.stamp, supporter_id)

    def supporter_rate(self, level: int, limit_break: int) -> int:
        return self.store.supporter_rate(level, limit_break)


def load(holding: Holding, source) -> dict:
    supporter = None
    supporter_rate = None
    if holding.supporter_id is not None:
        supporter = source.supporter(holding.supporter_id)
        supporter_rate = source.supporter_rate(
            holding.supporter_level, holding.supporter_limit_break
        )
    assembled = assemble(
        holding,
        source.unit(holding.unit_id),
        source.pilot(holding.pilot_id),
        supporter,
        supporter_rate,
    )
    return payload(assembled)


def parser() -> argparse.ArgumentParser:
    built = argparse.ArgumentParser()
    built.add_argument("--stamp", required=True)
    built.add_argument("--unit", type=int, required=True)
    built.add_argument("--level", type=int, required=True)
    built.add_argument("--pilot", type=int, required=True)
    built.add_argument("--pilot-level", type=int, required=True)
    built.add_argument("--limit-break", type=int, default=0)
    built.add_argument("--mech-sp", action="store_true")
    built.add_argument("--mech-ssp", action="store_true")
    built.add_argument("--weapon-level", type=int, default=5)
    built.add_argument("--supporter", type=int)
    built.add_argument("--supporter-level", type=int, default=1)
    built.add_argument("--supporter-limit-break", type=int, default=0)
    built.add_argument("--from-dump", type=Path)
    built.add_argument("--database-url")
    return built


def run(argv: list[str] | None = None) -> dict:
    args = parser().parse_args(argv)
    holding = Holding(
        stamp=args.stamp,
        unit_id=args.unit,
        level=args.level,
        pilot_id=args.pilot,
        pilot_level=args.pilot_level,
        limit_break=args.limit_break,
        mech_sp=args.mech_sp,
        mech_ssp=args.mech_ssp,
        weapon_level=args.weapon_level,
        supporter_id=args.supporter,
        supporter_level=args.supporter_level,
        supporter_limit_break=args.supporter_limit_break,
    )
    if args.from_dump is not None:
        catalog = Catalog.from_rows(normalize(holding.stamp, Dump.read(args.from_dump)))
        return load(holding, catalog)
    with Store(args.database_url) as store:
        return load(holding, StampedStore(store, holding.stamp))


def main() -> None:
    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
