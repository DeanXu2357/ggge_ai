"""Replay a run's saved frames through the current vision readers and diff
against the values recorded at capture time.

usage: uv run python scripts/replay_frames.py data/runs/<timestamp> [...]

The ledger already stores aligned (frame, read-values) tuples: every
frame-carrying event names its JPEG and the values the live reader saw on
the full-resolution screen. Re-running the readers over those frames turns
any observer change into a measurable regression -- the gate is "match
rates do not drop on the same corpus", not 100% (frames are 1280-long-edge
q85 JPEGs, so some degradation loss is expected and constant).

tactical_map events are not replayed: their recorded lists are world
coordinates accumulated across a whole camera sweep, which one frame
cannot reproduce.

A second pass feeds the event stream through BoardTracker and reports
belief/kill consistency (advisory: same-model units share one signature,
so a dead-sig reappearance is suspicious, not automatically wrong).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ggge_ai.battle import vision  # noqa: E402
from ggge_ai.battle.state import Faction  # noqa: E402
from ggge_ai.battle.tracker import SIG_ALIAS_MAX_DISTANCE, BoardTracker  # noqa: E402
from ggge_ai.battle.vision import (  # noqa: E402
    BattlePrepForecast,
    WeaponSelectForecast,
    signature_distance,
)

CANVAS = (2340, 1080)

WS_FIELDS = {
    "our_hp": "our_hp",
    "our_en": "our_en",
    "target_hp": "target_hp",
    "target_en": "target_en",
    "predicted_damage": "predicted_damage",
    "our_sig": "our_name_sig",
    "target_sig": "target_name_sig",
}
PREP_FIELDS = {
    "is_reaction": "is_reaction",
    "attack_value": "attack_value",
    "defense_value": "defense_value",
    "hit_pct": "hit_pct",
    "attacker_hp": "attacker_hp",
    "attacker_en": "attacker_en",
    "defender_hp": "defender_hp",
    "defender_en": "defender_en",
    "defender_hp_delta": "defender_hp_delta",
    "attacker_sig": "attacker_name_sig",
    "defender_sig": "defender_name_sig",
}


def _load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _load_frame(run_dir: Path, rel: str):
    img = cv2.imread(str(run_dir / rel))
    if img is None:
        return None
    if (img.shape[1], img.shape[0]) != CANVAS:
        img = cv2.resize(img, CANVAS, interpolation=cv2.INTER_CUBIC)
    return img


def _values_match(field: str, recorded, replayed) -> bool:
    if field.endswith("sig"):
        try:
            return signature_distance(recorded, replayed) <= SIG_ALIAS_MAX_DISTANCE
        except ValueError:
            return recorded == replayed
    return recorded == replayed


class Tally:
    def __init__(self) -> None:
        self.compared: dict[tuple[str, str], int] = defaultdict(int)
        self.matched: dict[tuple[str, str], int] = defaultdict(int)

    def add(self, kind: str, field: str, ok: bool) -> None:
        self.compared[(kind, field)] += 1
        if ok:
            self.matched[(kind, field)] += 1

    def render(self) -> str:
        lines = [f"{'reader/field':44s} {'match':>9s}"]
        for key in sorted(self.compared):
            kind, field = key
            lines.append(
                f"{kind + '.' + field:44s} {self.matched[key]:4d}/{self.compared[key]:<4d}"
            )
        return "\n".join(lines)


def _diff_event(event: dict, replayed, fields: dict[str, str], tally: Tally) -> None:
    for event_key, attr in fields.items():
        recorded = event.get(event_key)
        if recorded is None:
            continue
        value = getattr(replayed, attr) if replayed is not None else None
        tally.add(event["kind"], event_key, _values_match(event_key, recorded, value))


def _forecast_from_event(event: dict) -> WeaponSelectForecast:
    return WeaponSelectForecast(
        target_name_sig=event.get("target_sig"),
        target_hp=event.get("target_hp"),
        target_en=event.get("target_en"),
        predicted_damage=event.get("predicted_damage"),
        hit_pct=event.get("hit_pct"),
        our_name_sig=event.get("our_sig"),
        our_hp=event.get("our_hp"),
        our_en=event.get("our_en"),
    )


def _prep_from_event(event: dict) -> BattlePrepForecast:
    return BattlePrepForecast(
        is_reaction=bool(event.get("is_reaction")),
        attack_value=event.get("attack_value"),
        defense_value=event.get("defense_value"),
        hit_pct=event.get("hit_pct"),
        attacker_name_sig=event.get("attacker_sig"),
        attacker_hp=event.get("attacker_hp"),
        attacker_en=event.get("attacker_en"),
        defender_name_sig=event.get("defender_sig"),
        defender_hp=event.get("defender_hp"),
        defender_en=event.get("defender_en"),
        defender_hp_delta=event.get("defender_hp_delta"),
        support_defense=event.get("support_defense"),
    )


def replay_readers(run_dir: Path, events: list[dict]) -> tuple[Tally, int, int]:
    tally = Tally()
    missing = 0
    errors = 0
    for event in events:
        rel = event.get("frame")
        if not rel:
            continue
        kind = event["kind"]
        if kind not in ("forecast_weapon_select", "forecast_battle_prep", "select_unit"):
            continue
        frame = _load_frame(run_dir, rel)
        if frame is None:
            missing += 1
            continue
        try:
            if kind == "forecast_weapon_select":
                _diff_event(event, vision.read_weapon_select_forecast(frame), WS_FIELDS, tally)
            elif kind == "forecast_battle_prep":
                _diff_event(event, vision.read_battle_prep_forecast(frame), PREP_FIELDS, tally)
            elif kind == "select_unit":
                tally.add(kind, "unit_cards_present", vision.unit_cards_present(frame))
        except Exception as exc:  # noqa: BLE001 -- a reader crash is itself a finding
            errors += 1
            print(f"  reader error on {rel}: {exc!r}")
    return tally, missing, errors


def replay_tracker(events: list[dict]) -> str:
    tracker = BoardTracker()
    last_target: str | None = None
    reappearances: list[str] = []
    for event in events:
        kind = event["kind"]
        if kind == "forecast_weapon_select":
            sig = event.get("target_sig")
            if sig is not None:
                for dead_sig, belief in tracker.beliefs.items():
                    if belief.alive or belief.faction is not Faction.ENEMY:
                        continue
                    if signature_distance(sig, dead_sig) <= SIG_ALIAS_MAX_DISTANCE:
                        reappearances.append(
                            f"turn {event.get('turn')}: dead sig {dead_sig[:6]} "
                            f"reappears as forecast target"
                        )
            tracker.on_weapon_select(_forecast_from_event(event))
            last_target = sig
        elif kind == "forecast_battle_prep":
            tracker.on_battle_prep(_prep_from_event(event))
        elif kind == "kill_check":
            before, after = event.get("counter_before"), event.get("counter_after")
            if before and after and after[0] > before[0] and last_target is not None:
                belief = tracker.beliefs.get(last_target)
                if belief is not None:
                    belief.alive = False
                    belief.hp = 0
        elif kind == "next_turn" or kind == "turn":
            pass
    enemies = [b for b in tracker.beliefs.values() if b.faction is Faction.ENEMY]
    allies = [b for b in tracker.beliefs.values() if b.faction is Faction.ALLY]
    dead = [b for b in enemies if not b.alive]
    lines = [
        f"tracker: {len(tracker.beliefs)} beliefs "
        f"({len(enemies)} enemy, {len(allies)} ally), {len(dead)} dead"
    ]
    for note in reappearances:
        lines.append(f"  advisory: {note}")
    return "\n".join(lines)


def _iter_jsonl(paths: list[str]):
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(path.glob("battle_*.jsonl"))
        else:
            yield path


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    for jsonl in _iter_jsonl(sys.argv[1:]):
        run_dir = jsonl.parent
        events = _load_events(jsonl)
        print(f"=== {jsonl} ({len(events)} events) ===")
        tally, missing, errors = replay_readers(run_dir, events)
        print(tally.render())
        if missing or errors:
            print(f"frames missing: {missing}, reader errors: {errors}")
        print(replay_tracker(events))
        print()


if __name__ == "__main__":
    main()
