"""Offline books-closure check (silent-events batch C, issue #27).

Purely offline engineering analysis: it reads one battle ledger and asks how
much of the HP movement it recorded could be pinned on a named event. It never
runs live and its output must never seed a run (docs/agent-architecture.md 紅線;
docs/silent-events.md「全部產物 process-scoped，不當跨執行先驗」).

Anchor and reconstruction
--------------------------
The anchor is the per-turn `board_belief` snapshot (batch A): every our-turn the
controller serialises each unit's carried HP plus its freshness (`hp_turn`). We
group those snapshots by uid into a per-unit HP timeline and, between consecutive
snapshots, measure the gross HP movement (Σ|ΔHP|, sign-agnostic: a drop-then-fresh-
read counts both legs — it is "how much HP action happened", not the net).

The belief trajectory those snapshots trace already folds in every screen read:
the normal engagement path (forecast_weapon_select / forecast_battle_prep reads,
the kill outcome write) AND the batch-B audit overwrites. The audit overwrites are
the `unattributed_damage` events (batch B): a fresh screen read that diverged from
the carried belief past tolerance. So the total movement decomposes as

    total = engagement-attributed + attributed-kill + unknown-silent

where `unknown-silent` is exactly the non-kill `unattributed_damage` residual, and
`attributed-kill` is the `unattributed_damage` special case
`observed_hp == 0 and read_source == "outcome"` -- the last-known-HP-to-0 gap a
confirmed kill exposes, which we DID cause (we attacked and killed it) and so does
not count as an unexplained hole (docs/silent-events.md 批C).

Completeness score (numerator / denominator)
--------------------------------------------
Over the closeable units (ally + enemy; third-party gets a direction check only,
per spec 104-105):

    denominator = Σ_uid  total_movement[uid]          (all observed gross |ΔHP|)
    numerator   = denominator − Σ_uid unknown[uid]    (movement NOT left silent)
    完備性分數  = numerator / denominator
    未解殘差率  = 1 − 完備性分數 = Σ unknown / denominator

`unknown[uid]` = Σ|delta| over that unit's non-kill `unattributed_damage` events.
`total_movement[uid]` is the snapshot-derived gross movement, floored to
`unknown + attributed_kill` so sparse/stale snapshots can never report a residual
larger than the movement it is charged against.

Scope and honest limits
------------------------
The score measures, of the HP movement we DID observe, how much leaked as an
unexplained residual: a vision/tracker regression that makes more screen reads
diverge raises the residual and lowers the score, which is the intended regression
gauge (spec 用途 ②). It cannot see a hole where perception missed a change
entirely (belief went stale, nothing diverged, no snapshot caught the drop) --
that movement never enters the denominator. Old-format ledgers (no board_belief,
no unattributed_damage) degrade to "事件不足，無法閉合" rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .attribution import Event, _iter_paths, load_events

THIRD_PARTY = "third_party"

# the engagement chain: our-attack events that name the units a HP change flows
# through on the normal (attributed) read path. used to enrich the per-unit
# report, not to compute the score (they are sig-keyed, board_belief is
# uid-keyed; the score stands on snapshots + uid-keyed unattributed_damage).
ENGAGEMENT_KINDS = frozenset(
    {
        "forecast_weapon_select",
        "forecast_battle_prep",
        "kill_check",
        "attack",
        "engagement_confirm",
    }
)


def _is_attributed_kill(e: Event) -> bool:
    """An unattributed_damage residual that a confirmed kill explains: the belief
    went to a screen-confirmed 0 via the outcome write. We caused it, so it is
    accounted, not an unexplained silent event (docs/silent-events.md 批C)."""
    return e.get("observed_hp") == 0 and e.get("read_source") == "outcome"


@dataclass
class UnitLedger:
    uid: str
    faction: str
    hp_timeline: list[tuple[int, int | None]] = field(default_factory=list)
    total_movement: int = 0
    unknown_delta: int = 0
    kill_delta: int = 0
    unknown_count: int = 0
    kill_count: int = 0
    engagement_events: int = 0
    direction_violations: list[str] = field(default_factory=list)

    @property
    def closeable(self) -> bool:
        return self.faction != THIRD_PARTY

    @property
    def explained(self) -> int:
        return self.total_movement - self.unknown_delta


@dataclass
class ClosureReport:
    source: str
    outcome: str | None
    turns: int
    board_belief_snapshots: int
    unattributed_events: int
    degraded: bool = False
    degrade_reason: str | None = None
    units: list[UnitLedger] = field(default_factory=list)
    total_movement: int = 0
    unknown_total: int = 0
    kill_total: int = 0

    @property
    def completeness(self) -> float | None:
        if self.degraded or self.total_movement <= 0:
            return None
        return self.explained_total / self.total_movement

    @property
    def explained_total(self) -> int:
        return self.total_movement - self.unknown_total

    @property
    def unresolved_rate(self) -> float | None:
        c = self.completeness
        return None if c is None else 1.0 - c

    def render(self) -> str:
        lines = [
            f"帳目閉合檢查：{self.source}",
            f"  結果：{self.outcome}／回合數 {self.turns}",
            f"  錨點：board_belief 快照 {self.board_belief_snapshots} 筆、"
            f"unattributed_damage 事件 {self.unattributed_events} 筆",
        ]
        if self.degraded:
            lines.append(f"  [降級] {self.degrade_reason}")
            return "\n".join(lines)

        closeable = [u for u in self.units if u.closeable]
        third = [u for u in self.units if not u.closeable]

        lines.append("  單位帳目（我方＋敵方）：")
        if not closeable:
            lines.append("    （無可閉合單位）")
        for u in sorted(closeable, key=lambda x: (-x.unknown_delta, x.uid)):
            hp_first = _fmt_hp(u.hp_timeline[0][1]) if u.hp_timeline else "?"
            hp_last = _fmt_hp(u.hp_timeline[-1][1]) if u.hp_timeline else "?"
            lines.append(
                f"    {u.uid}（{u.faction}）HP {hp_first}→{hp_last}／"
                f"移動量 {u.total_movement}"
                f"（已解 {u.explained}、未解 {u.unknown_delta}）"
                f"；未解殘差 {u.unknown_count} 筆、"
                f"已歸因擊殺 {u.kill_count} 筆、交戰事件 {u.engagement_events} 筆"
            )

        if third:
            lines.append("  第三方單位（僅驗方向一致）：")
            for u in third:
                if u.direction_violations:
                    lines.append(
                        f"    {u.uid} 方向不一致 {len(u.direction_violations)} 處："
                        + "；".join(u.direction_violations)
                    )
                else:
                    lines.append(f"    {u.uid} 方向一致（HP 單調不增）")

        score = self.completeness
        if score is None:
            lines.append(
                "  完備性分數：未定義（board_belief 快照無可量測 HP 變化）"
            )
        else:
            lines.append(
                f"  完備性分數 = 已解 {self.explained_total} / 總移動 {self.total_movement}"
                f" = {score:.1%}"
            )
            lines.append(
                f"  未解殘差率 = 未解 {self.unknown_total} / 總移動 {self.total_movement}"
                f" = {self.unresolved_rate:.1%}"
                f"（已歸因擊殺 {self.kill_total} 不計入未解）"
            )
        return "\n".join(lines)


def _fmt_hp(hp: int | None) -> str:
    return "?" if hp is None else str(hp)


def _outcome(events: list[Event]) -> str | None:
    for e in events:
        if e["kind"] == "finish":
            return e.get("outcome")
    return None


def _turns(events: list[Event]) -> int:
    return max((int(e.get("turn", 1)) for e in events), default=0)


def _collect_snapshots(events: list[Event]) -> dict[str, list[dict[str, Any]]]:
    """Group board_belief unit rows by uid, in ledger (turn) order."""
    by_uid: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        if e["kind"] != "board_belief":
            continue
        turn = int(e.get("turn", 1))
        for row in e.get("units", []):
            uid = row.get("uid")
            if not uid:
                continue
            by_uid.setdefault(uid, []).append({**row, "turn": turn})
    return by_uid


def _movement_from_snapshots(rows: list[dict[str, Any]]) -> int:
    """Gross HP movement across a unit's snapshot timeline (Σ|ΔHP|). A snapshot
    with unknown HP (None) breaks the chain; a live→dead transition with the HP
    unread is charged the last-known HP (the unit fell to 0 unseen)."""
    movement = 0
    prev: dict[str, Any] | None = None
    for row in rows:
        if prev is not None:
            ph, ch = prev.get("hp"), row.get("hp")
            if ph is not None and ch is not None:
                movement += abs(ch - ph)
            elif ph is not None and prev.get("alive", True) and not row.get("alive", True):
                movement += abs(ph)
        prev = row
    return movement


def _direction_violations(rows: list[dict[str, Any]], recoveries: list[Event]) -> list[str]:
    """Third-party closure is direction-only (spec 104-105): HP should be
    monotonic non-increasing. A snapshot rise or a recovery residual is flagged."""
    out: list[str] = []
    prev: int | None = None
    for row in rows:
        hp = row.get("hp")
        if hp is not None and prev is not None and hp > prev:
            out.append(f"turn {row['turn']} HP {prev}→{hp} 上升")
        if hp is not None:
            prev = hp
    for e in recoveries:
        if isinstance(e.get("delta"), int) and e["delta"] > 0 and not _is_attributed_kill(e):
            out.append(f"turn {e.get('turn')} 未歸因回復 +{e['delta']}")
    return out


def close_events(events: list[Event], source: str = "<events>") -> ClosureReport:
    snapshots = _collect_snapshots(events)
    uatt = [e for e in events if e["kind"] == "unattributed_damage"]
    board_count = sum(1 for e in events if e["kind"] == "board_belief")

    report = ClosureReport(
        source=source,
        outcome=_outcome(events),
        turns=_turns(events),
        board_belief_snapshots=board_count,
        unattributed_events=len(uatt),
    )

    if board_count == 0:
        report.degraded = True
        if not uatt:
            report.degrade_reason = (
                "無 board_belief 快照且無 unattributed_damage 事件"
                "——舊格式流水帳，事件不足，無法閉合。"
            )
        else:
            report.degrade_reason = (
                "無 board_belief 快照（僅有 unattributed_damage 事件）"
                "——缺回合錨點無法重建 HP 時間線，無法閉合。"
            )
        return report

    uatt_by_uid: dict[str, list[Event]] = {}
    for e in uatt:
        uid = e.get("uid")
        if uid:
            uatt_by_uid.setdefault(uid, []).append(e)

    engagement_by_uid: dict[str, int] = {}
    for e in events:
        if e["kind"] not in ENGAGEMENT_KINDS:
            continue
        for key in ("uid", "target_uid", "our_uid", "attacker_uid", "defender_uid"):
            uid = e.get(key)
            if uid:
                engagement_by_uid[uid] = engagement_by_uid.get(uid, 0) + 1

    uids = set(snapshots) | set(uatt_by_uid)
    for uid in sorted(uids):
        rows = snapshots.get(uid, [])
        faction = _latest_faction(rows)
        led = UnitLedger(uid=uid, faction=faction)
        led.hp_timeline = [(r["turn"], r.get("hp")) for r in rows]
        led.engagement_events = engagement_by_uid.get(uid, 0)

        for e in uatt_by_uid.get(uid, []):
            delta = e.get("delta")
            mag = abs(delta) if isinstance(delta, int) else 0
            if _is_attributed_kill(e):
                led.kill_delta += mag
                led.kill_count += 1
            else:
                led.unknown_delta += mag
                led.unknown_count += 1

        movement = _movement_from_snapshots(rows)
        led.total_movement = max(movement, led.unknown_delta + led.kill_delta)

        if faction == THIRD_PARTY:
            led.direction_violations = _direction_violations(rows, uatt_by_uid.get(uid, []))

        report.units.append(led)

    closeable = [u for u in report.units if u.closeable]
    report.total_movement = sum(u.total_movement for u in closeable)
    report.unknown_total = sum(u.unknown_delta for u in closeable)
    report.kill_total = sum(u.kill_delta for u in closeable)
    return report


def _latest_faction(rows: list[dict[str, Any]]) -> str:
    for row in reversed(rows):
        f = row.get("faction")
        if f:
            return f
    return "unknown"


def close_file(path: str | Path) -> ClosureReport:
    p = Path(path)
    return close_events(load_events(p), source=str(p))


def close_target(target: str | Path) -> list[ClosureReport]:
    return [close_file(p) for p in _iter_paths(target)]


def run_summary(reports: list[ClosureReport]) -> str:
    """Aggregate completeness across a run's battles (denominator-weighted)."""
    scored = [r for r in reports if r.completeness is not None]
    degraded = [r for r in reports if r.degraded]
    lines = [f"run 總結：{len(reports)} 場（可評分 {len(scored)}、降級 {len(degraded)}）"]
    total = sum(r.total_movement for r in scored)
    unknown = sum(r.unknown_total for r in scored)
    if total > 0:
        lines.append(
            f"  加權完備性 = {(total - unknown)}/{total} = {(total - unknown) / total:.1%}"
            f"（未解殘差率 {unknown / total:.1%}）"
        )
    else:
        lines.append("  無可評分場次（皆降級或無可量測 HP 變化）。")
    return "\n".join(lines)
