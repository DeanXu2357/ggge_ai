"""Run one stage on the phone with the ggge_ai_2 agent.

usage:
  uv run python scripts/run_loop_v2.py --stage STAGE [--resurvey] [--keep-frames]
      [--serial R5CRC37JBYJ]

Start on the story stage list. --stage gives the id of the stage that the run enters.
The run does not check the id. The anthropic client reads ANTHROPIC_API_KEY from the
environment, and the stage store reads GGGE_DATABASE_URL. Evidence:
data/runs/<timestamp>/run.log, steps.jsonl and frames/. With --keep-frames, stream/ holds
every captured frame as <seq>.png and frames.csv gives the capture time of each seq.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from random import Random
from threading import Event
from types import FrameType

import anthropic

from ggge_ai_2.actuator.adb import AdbActuator
from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.loop import Agent, RunResult, cycle_log
from ggge_ai_2.agent.stage_plan_controller import StagePlanController, StageSurvey
from ggge_ai_2.agent.runlog import RunLog
from ggge_ai_2.interpreter.auto_cue import AutoCueInterpreter
from ggge_ai_2.interpreter.contract import Interpreter
from ggge_ai_2.interpreter.element_first import ElementFirstInterpreter
from ggge_ai_2.interpreter.elements.detectors import DETECTORS
from ggge_ai_2.interpreter.llm import LlmInterpreter
from ggge_ai_2.interpreter.llm_prompt import system_prompt
from ggge_ai_2.interpreter.logged import LoggedInterpreter
from ggge_ai_2.interpreter.power_save_cue import PowerSaveCueInterpreter
from ggge_ai_2.interpreter.unit_list_cue import UnitListCueInterpreter
from ggge_ai_2.mapgeom.stitch import StitchMapGeometry
from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.screenmodel.definition_model import DefinitionScreenModel
from ggge_ai_2.stagedata.store import PostgresStageStore
from ggge_ai_2.stream.adb import AdbScreencapStream
from ggge_ai_2.stream.contract import Stream
from ggge_ai_2.stream.kept import KeptStream
from ggge_ai_2.uisim.contract import Outcome, UiScreen, UiState
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages

SCREEN = (2340, 1080)
PACKAGE = "com.bandainamcoent.gget_WW"
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


@dataclass(frozen=True)
class NullDomain:
    def absorb(self, intent: object, outcome: Outcome | None) -> NullDomain:
        return self


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one stage on the phone.")
    parser.add_argument("--serial", default="R5CRC37JBYJ")
    parser.add_argument("--interpreter", choices=["llm"], default="llm")
    parser.add_argument("--stages", type=Path, default=Path("assets/ui_stages/stages.json"))
    parser.add_argument("--stage", required=True, help="the id of the stage that the run plays")
    parser.add_argument(
        "--trace-plans",
        action="store_true",
        help="write the input and the output of each plan step to run.log",
    )
    parser.add_argument(
        "--keep-frames",
        action="store_true",
        help="keep every captured frame and its capture time in the stream directory of the run",
    )
    parser.add_argument(
        "--auto-checked",
        action="store_true",
        help="start on the overview of a stage in progress; AUTO was turned off by hand",
    )
    parser.add_argument(
        "--resurvey",
        action="store_true",
        help="survey the stage again and compare the result with the stored data",
    )
    return parser.parse_args()


def app_version(serial: str) -> str:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "dumpsys", "package", PACKAGE],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    for line in result.stdout.splitlines():
        before, _, value = line.strip().partition("versionName=")
        if not before and value:
            return value
    raise RuntimeError(f"dumpsys shows no versionName of {PACKAGE}")


def code_version() -> str:
    """Return the short commit hash, with '-dirty' when tracked files have changes."""
    here = Path(__file__).resolve().parent
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=here
    ).stdout.strip()[:8]
    changes = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=True,
        cwd=here,
    ).stdout.strip()
    return f"{head}-dirty" if changes else head


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
    interpreter = PowerSaveCueInterpreter(
        LoggedInterpreter(
            ElementFirstInterpreter(DETECTORS, DefinitionScreenModel(), OpenCvMapParser())
        )
    )
    # Warning: the AUTO and unit list cues serve only the LLM interpreter. Remove them
    # together with it.
    fallback = AutoCueInterpreter(
        UnitListCueInterpreter(LoggedInterpreter(LlmInterpreter(client, system_prompt(raw_stages))))
    )

    versions = app_version(args.serial), code_version()
    # The run log keeps the seed, so that a replay of the survey takes the same swipes.
    seed = Random().getrandbits(32)
    with PostgresStageStore() as store:
        survey = StageSurvey(
            store,
            args.stage,
            *versions,
            args.resurvey,
            StitchMapGeometry(),
            Random(seed),
            args.auto_checked,
        )
        return play(
            args.serial,
            interpreter,
            fallback,
            uisim,
            survey,
            seed,
            args.trace_plans,
            args.keep_frames,
        )


def play(
    serial: str,
    interpreter: Interpreter,
    fallback: Interpreter,
    uisim: StageUiSim,
    survey: StageSurvey,
    seed: int,
    trace_plans: bool,
    keep_frames: bool,
) -> int:
    run_dir = Path("data/runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    configure_logging(run_dir)
    if trace_plans:
        logging.getLogger("ggge_ai_2.agent.trace").setLevel(logging.DEBUG)
    stop = Event()
    stop_on_interrupt(stop)
    logging.getLogger(__name__).info(
        "stage",
        extra={
            "stage": survey.stage,
            "app_version": survey.app_version,
            "code_version": survey.code_version,
            "resurvey": survey.resurvey,
            "seed": seed,
        },
    )
    stream: Stream = AdbScreencapStream(serial)
    with ExitStack() as stack:
        if keep_frames:
            stream = stack.enter_context(KeptStream(stream, run_dir / "stream"))
        agent = Agent(
            stream=stream,
            actuator=AdbActuator(serial),
            interpreter=interpreter,
            fallback=fallback,
            uisim=uisim,
            plan_controller=StagePlanController(UiScreen.DROP_REWARD_RESULT, uisim, SCREEN, survey),
            belief=Belief(
                ui=UiState(UiScreen.STORY_STAGE_LIST),
                ui_basis=UiBasis(UiSource.ASSUMED),
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
                plan_controller=StagePlanController(UiScreen.STORY_STAGE_LIST, uisim, SCREEN),
                belief=agent.belief,
                stop=agent.stop,
            )
            back = run_phase(agent)
            print(f"phase 2 (to {UiScreen.STORY_STAGE_LIST}): {back}")
    print(f"run directory: {run_dir}")
    return 0 if clear is RunResult.DONE and back is RunResult.DONE else 1


if __name__ == "__main__":
    sys.exit(main())
