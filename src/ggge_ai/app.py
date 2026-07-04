from __future__ import annotations

from pathlib import Path

import uiautomator2 as u2

from .actuation.adb import AdbActuator
from .perception.adb.perception import AdbPerception
from .vision.manifest import TemplateManifest
from .vision.pipeline import RecognizerPipeline, Stage

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "assets" / "templates"
DEBUG_SHOTS = PROJECT_ROOT / "assets" / "run-shots"


def build_perception(
    device, manifest: TemplateManifest | None = None, save_shots: bool = False
) -> AdbPerception:
    manifest = manifest or TemplateManifest.load(TEMPLATE_ROOT)
    recognizer = manifest.build_recognizer()
    pipeline = RecognizerPipeline(
        screen_stages=[Stage(recognizer, accept_above=0.90)],
        element_stages=[Stage(recognizer, accept_above=0.80)],
    )
    return AdbPerception(
        device=device,
        pipeline=pipeline,
        element_ids_by_screen=manifest.element_ids_by_screen(),
        screenshot_dir=DEBUG_SHOTS if save_shots else None,
    )


def connect(save_shots: bool = False) -> tuple[AdbPerception, AdbActuator]:
    device = u2.connect()
    return build_perception(device, save_shots=save_shots), AdbActuator(device)
