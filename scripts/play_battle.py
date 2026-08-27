"""Play one battle through the engine in the command mode and write the log."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ggge_ai.engine.client import BattleEngine  # noqa: E402
from ggge_ai.engine.contract import DiceMode  # noqa: E402
from ggge_ai.engine.play import FORCED_HITS, Player  # noqa: E402
from ggge_ai.engine.session import EngineSession  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Command mode: one battle through the engine")
    parser.add_argument("--scenario", required=True, help="the scenario file (sandbox-scenario/1)")
    parser.add_argument("--engine", required=True, help="the built engine binary")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument("--out", default=None, help="the run directory; default data/runs/<timestamp>")
    parser.add_argument(
        "--forced-hits",
        action="store_true",
        help="every chance event lands; use for a run that must end on placeholder data",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    out = Path(args.out or Path("data/runs") / time.strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    dice = dict(FORCED_HITS) if args.forced_hits else {"mode": str(DiceMode.SAMPLED)}
    with BattleEngine(args.engine) as engine:
        EngineSession.from_scenario(args.scenario, engine, seed=args.seed)
        outcome = Player(engine, dice=dice).play(max_turns=args.max_turns)
        final = engine.call("export")
    (out / "play.json").write_text(
        json.dumps(
            {
                "seed": args.seed,
                "dice": dice,
                "gone": outcome.gone,
                "turn": outcome.turn,
                "log": outcome.log,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    (out / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"turn {outcome.turn}, gone {outcome.gone}, {len(outcome.log)} activations, log in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
