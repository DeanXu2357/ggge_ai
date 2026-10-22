import json
from pathlib import Path
from typing import Any

import pytest

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.llm_prompt import system_prompt

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"


def _real_stages() -> dict[str, Any]:
    return json.loads(REAL_STAGES.read_text(encoding="utf-8"))


def test_prompt_names_every_screen_except_power_save() -> None:
    prompt = system_prompt(_real_stages())

    for screen in Screen:
        if screen in (Screen.POWER_SAVE_LOCK, Screen.POWER_SAVE_DIM):
            assert screen.value not in prompt
        else:
            assert f"- {screen.value} " in prompt or f"- {screen.value}:" in prompt


def test_prompt_is_identical_across_calls() -> None:
    assert system_prompt(_real_stages()) == system_prompt(_real_stages())


def test_missing_screen_raises_key_error() -> None:
    stages = _real_stages()
    stages["screens"] = [s for s in stages["screens"] if s["name"] != Screen.SORTIE_PREP.value]

    with pytest.raises(KeyError):
        system_prompt(stages)
