"""goal 輸入解析、執行組裝、停止報告。"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import Constraint, GoalSpec, Objective
from .runtime.journal import Journal, rotate_runs
from .strategy import htn
from .strategy.domain import build_domain, root_task
from .strategy.ledger import Ledger, OfflineLedger

RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "strategy.jsonl"
REPORT_NAME = "report.json"


@dataclass(frozen=True)
class StopReport:
    kind: str
    reason: str
    goal: GoalSpec
    state: dict[str, Any]
    journal: str
    dry_run: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "goal": {
                "stage": self.goal.stage,
                "objectives": sorted(item.value for item in self.goal.objectives),
                "constraint": self.goal.constraint.value,
            },
            "state": self.state,
            "detail": self.detail,
            "journal": self.journal,
            "dry_run": self.dry_run,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)
        path.write_text(text + "\n", encoding="utf-8")


def parse_objectives(text: str) -> frozenset[Objective]:
    names = [part.strip() for part in text.split(",") if part.strip()]
    if not names:
        raise argparse.ArgumentTypeError("objectives 不得為空")
    known = {item.value for item in Objective}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"未知的目標項目 {', '.join(unknown)}；可用：{', '.join(sorted(known))}"
        )
    return frozenset(Objective(name) for name in names)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ggge_ai")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--objectives", type=parse_objectives, default=parse_objectives("clear"))
    parser.add_argument(
        "--constraint", choices=[item.value for item in Constraint], default="split"
    )
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def goal_from_args(args: argparse.Namespace) -> GoalSpec:
    return GoalSpec(
        stage=args.stage,
        objectives=args.objectives,
        constraint=Constraint(args.constraint),
    )


def resolve_run_dir(run_dir: str | None, runs_root: Path = RUNS_ROOT) -> Path:
    if run_dir is not None:
        return Path(run_dir)
    return runs_root / time.strftime("%Y%m%d-%H%M%S")


def rotate_default_runs(run_dir: str | None, runs_root: Path = RUNS_ROOT) -> tuple[Path, ...]:
    """明確指定 run 目錄（測試注入、外部工具接管）就不動 runs root。"""
    if run_dir is not None:
        return ()
    return rotate_runs(runs_root)


def run(goal: GoalSpec, run_dir: Path, dry_run: bool) -> StopReport:
    journal = Journal(run_dir / JOURNAL_NAME)
    journal.record(
        "run_start",
        stage=goal.stage,
        objectives=sorted(item.value for item in goal.objectives),
        constraint=goal.constraint.value,
        dry_run=dry_run,
    )

    ledger: Ledger = OfflineLedger() if dry_run else Ledger()
    ledger.sync()
    journal.record("ledger_sync", synced=ledger.synced, resources=dict(ledger.resources))

    domain = build_domain()
    state = ledger.symbols()
    task = root_task(goal)
    journal.record("htn_root", task=task.name)

    result = htn.decompose(domain, state, [task])
    if isinstance(result, htn.NoApplicableMethod):
        report = StopReport(
            kind="no_applicable_method",
            reason=result.describe(),
            goal=goal,
            state=dict(state),
            journal=JOURNAL_NAME,
            dry_run=dry_run,
            detail={"task": result.task.name, "tried": list(result.tried)},
        )
    else:
        report = StopReport(
            kind="not_implemented",
            reason="HTN 分解出計畫，但批 0 沒有執行器",
            goal=goal,
            state=dict(result.state),
            journal=JOURNAL_NAME,
            dry_run=dry_run,
            detail={"plan": [step.name for step in result.plan]},
        )

    journal.record("stop", stop_kind=report.kind, reason=report.reason, detail=report.detail)
    report.write(run_dir / REPORT_NAME)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("批 0 只實作 --dry-run")
    goal = goal_from_args(args)
    archives = rotate_default_runs(args.run_dir)
    if archives:
        print(f"rotated {len(archives)} old run dir(s)")
    run_dir = resolve_run_dir(args.run_dir)
    report = run(goal, run_dir, dry_run=True)
    print(f"{report.kind}: {report.reason}")
    print(f"run dir: {run_dir}")
    return 0
