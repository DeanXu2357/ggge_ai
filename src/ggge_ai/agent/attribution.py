"""Post-battle attribution v1: split a battle into growth gaps vs code defects.

Purely observational (docs/agent-architecture.md「戰後歸因（觀測式，非模擬式）」):
it reads one battle ledger and turns the recorded evidence into structured
diagnoses. Every diagnosis is tagged either 數值差距 (spend resources / develop
the team, strategic layer) or 程式缺陷 (fix our program). No simulation, no
prior across runs.

The current ledger schema carries positions, actions and outcomes but no
per-engagement damage, no unit identity and no per-turn full census. Growth
diagnoses that need those (firepower shortfall, attrition, roster short-board)
therefore stay dormant unless the ledger carries the optional fields listed in
`_DAMAGE_FIELDS` / `_KO_KINDS`; when the data is absent the report says so
(coverage notes) instead of guessing. Code defects are fully derivable today.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import json

Event = dict[str, Any]


class DiagClass(str, Enum):
    GROWTH = "數值差距"
    CODE = "程式缺陷"
    INCONCLUSIVE = "無法判定"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class DiagCode(str, Enum):
    STALL_DEFECT = "stall_defect"
    SEEK_DEFECT = "seek_defect"
    SKILL_DEFECT = "skill_defect"
    FIREPOWER_GAP = "firepower_gap"
    ATTRITION_GAP = "attrition_gap"
    ROSTER_GAP = "roster_gap"


_SEVERITY_WEIGHT = {Severity.INFO: 0, Severity.WARN: 1, Severity.CRITICAL: 2}

RESOLVED_OUTCOMES = frozenset({"battle_result"})
STUCK_OUTCOMES = frozenset({"idle_timeout"})
ABORTED_OUTCOMES = frozenset({"interrupted"})

# Standby reasons that mean「打不到／走不到」→ 索敵/機動 (code), vs EN depletion.
_EN_REASONS = frozenset({"en", "en_depleted", "out_of_en", "no_en", "low_en"})
_RANGE_REASONS = frozenset({"out_of_range", "no_target", "unreachable"})

# Optional forward-compat fields; when a ledger starts carrying real numbers the
# growth diagnoses light up without touching this logic.
_DAMAGE_FIELDS = ("actual_damage", "damage", "dealt")
_ENEMY_HP_FIELDS = ("enemy_hp_before", "enemy_hp_after")
_KO_KINDS = frozenset({"ally_lost", "ally_ko", "unit_lost"})

# Thresholds (tuned against the three 2026-07-05 real ledgers; see report).
STALL_IDLE_GAP_S = 120.0
PASSIVE_SHARE_STRONG = 0.50
PASSIVE_SHARE_MODERATE = 0.30
PASSIVE_COUNT_MIN = 5
FIREPOWER_DENT_RATIO = 0.05


@dataclass
class Finding:
    code: DiagCode
    diag_class: DiagClass
    severity: Severity
    evidence: str
    recommendation: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttributionReport:
    source: str
    outcome: str | None
    resolved: bool
    findings: list[Finding] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> DiagClass:
        actionable = [f for f in self.findings if f.severity is not Severity.INFO]
        if not actionable:
            return DiagClass.INCONCLUSIVE
        top = max(actionable, key=lambda f: _SEVERITY_WEIGHT[f.severity])
        return top.diag_class

    def render(self) -> str:
        lines = [
            f"戰後歸因報告：{self.source}",
            f"  結果：{self.outcome}（{'已分勝負' if self.resolved else '未分勝負/中斷'}）",
            f"  主判定：{self.verdict.value}",
        ]
        m = self.metrics
        lines.append(
            "  指標："
            f"時長 {m.get('duration_s', 0):.0f}s、"
            f"收尾閒置 {m.get('idle_gap_s', 0):.0f}s、"
            f"出擊活化 {m.get('activations', 0)} 次"
            f"（攻擊 {m.get('offensive_activations', 0)}／"
            f"被動 {m.get('passive_activations', 0)}，"
            f"被動占比 {m.get('passive_share', 0):.0%}）"
        )
        if m.get("decisions"):
            lines.append(
                "  對帳鏈："
                f"決策 {m['decisions']}（grounded {m['grounded_decisions']}）、"
                f"擊殺驗證 {m.get('kill_confirmed', 0)}/{m.get('kill_checks', 0)} 確認、"
                f"模擬脫軌 {m.get('sim_diverges', 0)}、"
                f"機率分支 {m.get('rng_branches', 0)}、"
                f"模型錯誤 {m.get('model_diverges', 0)}、"
                f"演算法歸功比 {m.get('algorithm_credit', 0):.0%}"
            )
        if not self.findings:
            lines.append("  無異常發現。")
        for f in self.findings:
            lines.append(f"  [{f.severity.value.upper()}] {f.code.value} → {f.diag_class.value}")
            lines.append(f"      證據：{f.evidence}")
            lines.append(f"      建議：{f.recommendation}")
        for note in self.coverage_notes:
            lines.append(f"  （資料覆蓋）{note}")
        return "\n".join(lines)


def load_events(path: str | Path) -> list[Event]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _reason_class(reason: str | None) -> str:
    if reason in _EN_REASONS:
        return "en"
    if reason in _RANGE_REASONS:
        return "range"
    return "other"


def _activations(events: list[Event]) -> list[dict[str, Any]]:
    """Segment the log by `select_unit` into our-unit activations.

    Each activation records whether the unit attacked or ended passive (standby),
    and the standby reason class. Enemy-phase `engagement_confirm` bursts between
    activations are ignored — they are not our decisions.
    """
    acts: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for e in events:
        kind = e["kind"]
        if kind == "select_unit":
            cur = {"attacked": False, "standby": False, "reason": None}
            acts.append(cur)
            continue
        if cur is None:
            continue
        if kind == "attack":
            cur["attacked"] = True
        elif kind == "standby":
            cur["standby"] = True
            cur["reason"] = e.get("reason")
    return acts


def _compute_metrics(events: list[Event]) -> dict[str, Any]:
    outcome = None
    for e in events:
        if e["kind"] == "finish":
            outcome = e.get("outcome")

    non_finish = [e for e in events if e["kind"] != "finish"]
    duration = events[-1]["t"] if events else 0.0
    idle_gap = round(duration - non_finish[-1]["t"], 1) if non_finish else 0.0

    acts = _activations(events)
    passive = [a for a in acts if a["standby"] and not a["attacked"]]
    offensive = [a for a in acts if a["attacked"]]
    reason_classes: dict[str, int] = {"en": 0, "range": 0, "other": 0}
    for a in passive:
        reason_classes[_reason_class(a["reason"])] += 1

    tac = next((e for e in events if e["kind"] == "tactical_map"), None)
    ko = sum(1 for e in events if e["kind"] in _KO_KINDS)

    def _num(e: Event, keys: tuple[str, ...]) -> float | None:
        for k in keys:
            if isinstance(e.get(k), (int, float)):
                return float(e[k])
        return None

    damages = [d for e in events if (d := _num(e, _DAMAGE_FIELDS)) is not None]

    decisions = [e for e in events if e["kind"] == "decision"]
    grounded = [e for e in decisions if e.get("quality") == "grounded"]
    kill_checks = [e for e in events if e["kind"] == "kill_check"]
    confirmed = [e for e in kill_checks if e.get("result") == "confirmed"]
    confirmed_grounded = [e for e in confirmed if e.get("quality") == "grounded"]
    offensive_n = len(offensive)

    return {
        "decisions": len(decisions),
        "grounded_decisions": len(grounded),
        "kill_checks": len(kill_checks),
        "kill_confirmed": len(confirmed),
        "kill_confirmed_grounded": len(confirmed_grounded),
        "rng_branches": sum(1 for e in events if e["kind"] == "rng_branch"),
        "model_diverges": sum(1 for e in events if e["kind"] == "model_diverge"),
        "sim_diverges": sum(1 for e in events if e["kind"] == "sim_diverge"),
        "sim_skips": sum(1 for e in events if e["kind"] == "sim_skip"),
        "algorithm_credit": (len(confirmed_grounded) / offensive_n) if offensive_n else 0.0,
        "outcome": outcome,
        "duration_s": duration,
        "idle_gap_s": idle_gap,
        "activations": len(acts),
        "offensive_activations": len(offensive),
        "passive_activations": len(passive),
        "passive_share": (len(passive) / len(acts)) if acts else 0.0,
        "passive_reason_range": reason_classes["range"],
        "passive_reason_en": reason_classes["en"],
        "opening_enemies": len(tac["enemies"]) if tac else None,
        "opening_allies": len(tac["allies"]) if tac else None,
        "ko_events": ko,
        "damage_samples": len(damages),
        "median_damage": _median(damages) if damages else None,
    }


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def attribute_events(events: list[Event], source: str = "<events>") -> AttributionReport:
    m = _compute_metrics(events)
    outcome = m["outcome"]
    resolved = outcome in RESOLVED_OUTCOMES
    report = AttributionReport(
        source=source, outcome=outcome, resolved=resolved, metrics=m
    )

    _diagnose_stall(report, m)
    _diagnose_seek(report, m)
    _diagnose_skill(report, m)
    _diagnose_firepower(report, m)
    _note_growth_coverage(report, m)
    return report


def _diagnose_stall(report: AttributionReport, m: dict[str, Any]) -> None:
    outcome = m["outcome"]
    stuck = outcome in STUCK_OUTCOMES
    long_idle = m["idle_gap_s"] >= STALL_IDLE_GAP_S
    if outcome in ABORTED_OUTCOMES:
        report.findings.append(
            Finding(
                code=DiagCode.STALL_DEFECT,
                diag_class=DiagClass.INCONCLUSIVE,
                severity=Severity.INFO,
                evidence=f"結果為 {outcome}（操作端中斷），非戰鬥結果，不歸因。",
                recommendation="重跑該場取得完整流水帳後再判定。",
                metrics={"idle_gap_s": m["idle_gap_s"]},
            )
        )
        return
    if stuck or long_idle:
        report.findings.append(
            Finding(
                code=DiagCode.STALL_DEFECT,
                diag_class=DiagClass.CODE,
                severity=Severity.CRITICAL,
                evidence=(
                    f"結果 {outcome}；最後一個動作到收尾閒置 {m['idle_gap_s']:.0f}s"
                    f"（門檻 {STALL_IDLE_GAP_S:.0f}s）——畫面卡住、未標定或回合耗盡未分勝負。"
                ),
                recommendation="改程式：補該卡住畫面（WARNING/彈窗）的錨點與推進，非養成問題。",
                metrics={"idle_gap_s": m["idle_gap_s"], "outcome": outcome},
            )
        )


def _diagnose_seek(report: AttributionReport, m: dict[str, Any]) -> None:
    rng = m["passive_reason_range"]
    share = m["passive_share"]
    if rng < PASSIVE_COUNT_MIN and share < PASSIVE_SHARE_MODERATE:
        return
    if share >= PASSIVE_SHARE_STRONG:
        sev = Severity.WARN
        head = "大量出擊活化以待機收場"
    elif share >= PASSIVE_SHARE_MODERATE or rng >= PASSIVE_COUNT_MIN:
        sev = Severity.INFO
        head = "部分出擊活化以待機收場"
    else:
        return
    report.findings.append(
        Finding(
            code=DiagCode.SEEK_DEFECT,
            diag_class=DiagClass.CODE,
            severity=sev,
            evidence=(
                f"{head}：被動占比 {share:.0%}"
                f"（被動 {m['passive_activations']}／活化 {m['activations']}），"
                f"其中 out_of_range/走不到 {rng} 次。"
            ),
            recommendation="改程式：強化索敵與移動（朝遠處敵人前進），別原地待機。",
            metrics={
                "passive_share": share,
                "passive_reason_range": rng,
                "activations": m["activations"],
            },
        )
    )


def _diagnose_skill(report: AttributionReport, m: dict[str, Any]) -> None:
    en = m["passive_reason_en"]
    if en <= 0:
        return
    report.findings.append(
        Finding(
            code=DiagCode.SKILL_DEFECT,
            diag_class=DiagClass.CODE,
            severity=Severity.WARN,
            evidence=f"{en} 次待機原因為 EN 耗盡，卻沒有動用技能/SUPPORT 補 EN。",
            recommendation="改程式：行動掃描接上技能/SUPPORT（EN 補給、回血）使用。",
            metrics={"passive_reason_en": en},
        )
    )


def _diagnose_firepower(report: AttributionReport, m: dict[str, Any]) -> None:
    if not m["damage_samples"]:
        return
    med = m["median_damage"] or 0.0
    if med > 0:
        report.findings.append(
            Finding(
                code=DiagCode.FIREPOWER_GAP,
                diag_class=DiagClass.GROWTH,
                severity=Severity.INFO,
                evidence=f"實測傷害中位數 {med:.0f}（樣本 {m['damage_samples']}）。",
                recommendation="若相對敵方 HP 偏低，屬火力不足，往武器強化（戰略層）。",
                metrics={"median_damage": med, "damage_samples": m["damage_samples"]},
            )
        )


def _note_growth_coverage(report: AttributionReport, m: dict[str, Any]) -> None:
    if not m["damage_samples"]:
        report.coverage_notes.append(
            "火力不足（→養成）無法判定：流水帳未帶每次交戰的實測傷害/敵 HP。"
        )
    if not m["ko_events"]:
        report.coverage_notes.append(
            "陣亡歸因（→養成）與編成短板無法判定：流水帳未帶我方陣亡事件與單位身分。"
        )
    resolved = m["outcome"] in RESOLVED_OUTCOMES
    if not m.get("decisions"):
        if resolved:
            report.coverage_notes.append(
                "勝利歸因無法判定：流水帳沒有 decision 事件（對帳鏈未運作）。"
            )
        return
    if resolved and not m.get("grounded_decisions"):
        report.coverage_notes.append(
            "勝利不可歸因演算法：所有攻擊決策都缺乏 grounded 模擬期望"
            "（[SIM-SKIP]）——這場贏的是隊伍數值，不是演算法。"
        )
    elif resolved and m.get("algorithm_credit", 0) == 0:
        report.coverage_notes.append(
            "勝利不可歸因演算法：沒有任何 grounded 決策通過擊殺驗證。"
        )


def attribute_file(path: str | Path) -> AttributionReport:
    p = Path(path)
    return attribute_events(load_events(p), source=str(p))


def attribute_ledger(ledger: Any, source: str = "<ledger>") -> AttributionReport:
    """Attribute a live BattleLedger via its read-only `.events` (no coupling)."""
    return attribute_events(list(ledger.events), source=source)


def attribute_run_dir(run_dir: str | Path) -> list[AttributionReport]:
    d = Path(run_dir)
    files = sorted(d.glob("battle_*.jsonl"))
    return [attribute_file(f) for f in files]


def _iter_paths(target: str | Path) -> Iterable[Path]:
    p = Path(target)
    if p.is_dir():
        yield from sorted(p.glob("battle_*.jsonl"))
    else:
        yield p
