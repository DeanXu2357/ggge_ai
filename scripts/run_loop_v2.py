"""Run one stage on the phone with the ggge_ai_2 agent.

usage:
  uv run python scripts/run_loop_v2.py [--serial R5CRC37JBYJ]

Start on the story stage list. The anthropic client reads ANTHROPIC_API_KEY from the
environment. Evidence: data/runs/<timestamp>/run.log, steps.jsonl and frames/.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Event
from types import FrameType

import anthropic

from ggge_ai_2.actuator.adb import AdbActuator
from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.loop import Agent, RunResult, cycle_log
from ggge_ai_2.agent.plan_controller import (
    PassingWait,
    PowerSaveUnlock,
    StagePlanController,
    TapToContinue,
)
from ggge_ai_2.agent.runlog import RunLog
from ggge_ai_2.interpreter.auto_cue import AutoCueInterpreter
from ggge_ai_2.interpreter.llm import LlmInterpreter
from ggge_ai_2.interpreter.llm_prompt import system_prompt
from ggge_ai_2.mapgeom.contract import Alignment, KnownMap, LocalBoard
from ggge_ai_2.mapparser.contract import MapReading, ScreenPoint, ViewCell
from ggge_ai_2.stream.adb import AdbScreencapStream
from ggge_ai_2.stream.contract import Frame
from ggge_ai_2.uisim.contract import Outcome, UiScreen, UiState
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages

SCREEN = (2340, 1080)
_RECORD_FIELDS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **{key: value for key, value in vars(record).items() if key not in _RECORD_FIELDS},
        }
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


class NullMapParser:
    def parse(self, frame: Frame) -> MapReading | None:
        return None

    def locate(self, frame: Frame, cell: ViewCell) -> ScreenPoint | None:
        return None


class NullMapGeometry:
    def align(
        self, board: LocalBoard, known: KnownMap, prior: Alignment | None
    ) -> Alignment | None:
        return None

    def merge(self, known: KnownMap, board: LocalBoard, alignment: Alignment) -> KnownMap:
        return known


@dataclass(frozen=True)
class NullDomain:
    def absorb(self, intent: object, outcome: Outcome | None) -> NullDomain:
        return self


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one stage on the phone.")
    parser.add_argument("--serial", default="R5CRC37JBYJ")
    parser.add_argument("--interpreter", choices=["llm"], default="llm")
    parser.add_argument("--stages", type=Path, default=Path("assets/ui_stages/stages.json"))
    return parser.parse_args()


def on_terminal(record: logging.LogRecord) -> bool:
    if record.name == cycle_log.name:
        return True
    return record.levelno >= logging.WARNING and record.name.startswith("ggge_ai_2")


def configure_logging(run_dir: Path) -> None:
    to_file = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    to_file.setFormatter(JsonLineFormatter())
    to_stderr = logging.StreamHandler(sys.stderr)
    to_stderr.setLevel(logging.INFO)
    to_stderr.addFilter(on_terminal)
    to_stderr.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[to_file, to_stderr])
    for noisy in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run_phase(agent: Agent) -> RunResult:
    try:
        return agent.run()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Ctrl-C sends SIGINT to the adb child too. The adb call then fails.
        if agent.stop.is_set():
            return RunResult.STOPPED
        raise


def stop_on_interrupt(stop: Event) -> None:
    def handle(signum: int, frame: FrameType | None) -> None:
        if stop.is_set():
            signal.default_int_handler(signum, frame)
        stop.set()

    signal.signal(signal.SIGINT, handle)


def main() -> int:
    args = parse_args()
    with args.stages.open(encoding="utf-8") as stages_file:
        raw_stages = json.load(stages_file)
    uisim = StageUiSim(load_stages(args.stages))
    client = anthropic.Anthropic()
    if client.api_key is None:
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 2
    interpreter = AutoCueInterpreter(LlmInterpreter(client, system_prompt(raw_stages)))
    reflexes = (PowerSaveUnlock(), PassingWait(), TapToContinue(SCREEN))

    run_dir = Path("data/runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    configure_logging(run_dir)
    stop = Event()
    stop_on_interrupt(stop)

    agent = Agent(
        stream=AdbScreencapStream(args.serial),
        actuator=AdbActuator(args.serial),
        interpreter=interpreter,
        mapparser=NullMapParser(),
        mapgeom=NullMapGeometry(),
        uisim=uisim,
        plan_controller=StagePlanController(UiScreen.DROP_REWARD_RESULT, reflexes, uisim, SCREEN),
        belief=Belief(
            ui=UiState(UiScreen.STORY_STAGE_LIST),
            ui_basis=UiBasis(UiSource.ASSUMED),
            camera=None,
            known_map=KnownMap({}),
            domain=NullDomain(),
            as_of=None,
        ),
        stop=stop,
        runlog=RunLog(run_dir),
    )
    clear = run_phase(agent)
    print(f"phase 1 (to {UiScreen.DROP_REWARD_RESULT}): {clear}")
    back = None
    if clear is RunResult.DONE:
        agent = replace(
            agent,
            plan_controller=StagePlanController(UiScreen.STORY_STAGE_LIST, reflexes, uisim, SCREEN),
            belief=agent.belief,
            stop=agent.stop,
        )
        back = run_phase(agent)
        print(f"phase 2 (to {UiScreen.STORY_STAGE_LIST}): {back}")
    print(f"run directory: {run_dir}")
    return 0 if clear is RunResult.DONE and back is RunResult.DONE else 1


if __name__ == "__main__":
    sys.exit(main())
