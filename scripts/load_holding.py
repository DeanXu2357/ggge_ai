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
from pathlib import Path

from ggge_ai.gamedata.holding import Holding, assemble, payload
from ggge_ai.gamedata.normalize import Dump, normalize
from ggge_ai.gamedata.records import Catalog
from ggge_ai.gamedata.store import Store


def load(holding: Holding, catalog: Catalog) -> dict:
    supporter = None
    supporter_rate = None
    if holding.supporter_id is not None:
        supporter = catalog.supporter(holding.supporter_id)
        supporter_rate = catalog.supporter_rate(
            holding.supporter_level, holding.supporter_limit_break
        )
    assembled = assemble(
        holding,
        catalog.unit(holding.unit_id),
        catalog.pilot(holding.pilot_id),
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
    built.add_argument("--supporter-level", type=int)
    built.add_argument("--supporter-limit-break", type=int)
    built.add_argument("--from-dump", type=Path)
    built.add_argument("--database-url")
    return built


def _crew_flags(built: argparse.ArgumentParser, args: argparse.Namespace) -> dict:
    named = args.supporter_level is not None or args.supporter_limit_break is not None
    if args.supporter is None:
        if named:
            built.error("--supporter-level and --supporter-limit-break need --supporter")
        return {}
    if args.supporter_level is None or args.supporter_limit_break is None:
        built.error("--supporter needs --supporter-level and --supporter-limit-break")
    return {
        "supporter_id": args.supporter,
        "supporter_level": args.supporter_level,
        "supporter_limit_break": args.supporter_limit_break,
    }


def run(argv: list[str] | None = None) -> dict:
    built = parser()
    args = built.parse_args(argv)
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
        **_crew_flags(built, args),
    )
    if args.from_dump is not None:
        return load(holding, Catalog.from_rows(normalize(holding.stamp, Dump.read(args.from_dump))))
    with Store(args.database_url) as store:
        return load(holding, Catalog.from_rows(store.read_rows(holding.stamp)))


def main() -> None:
    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
