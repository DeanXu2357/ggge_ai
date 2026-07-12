"""Local-LLM screen reading: a fallback describer for frames nothing in the
template stack recognizes.

Templates and classifiers stay the primary perception (cheap, deterministic);
the LLM is consulted only for unknown scenes and failed-transition
diagnostics, and its output is advisory -- logged and archived, never given
direct control authority. Model choice is measured, not assumed: on this
machine gemma4:latest (8B) reads a battle frame in ~3.6s warm with clean
JSON, while gemma4:26b is slower (~11s) and messier (2026-07-12 probe).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

log = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:latest"
MAX_EDGE = 1280
JPEG_QUALITY = 85

PROMPT = (
    "You are reading a screenshot from the mobile game SD Gundam G Generation "
    "ETERNAL (Traditional Chinese UI, landscape). Answer in JSON with keys: "
    '"scene" (short English guess of what screen this is), '
    '"visible_text" (list of the most important on-screen strings, verbatim), '
    '"dialog" (true if a story/dialog box with text is showing), '
    '"buttons" (list of tappable buttons/labels you can see), '
    '"suggestion" (one short sentence: what tap would advance this screen).'
)


@dataclass
class ScreenReading:
    scene: str
    visible_text: list[str]
    dialog: bool
    buttons: list[str]
    suggestion: str
    latency_s: float

    def summary(self) -> str:
        texts = ", ".join(str(t) for t in self.visible_text[:5])
        return (
            f"scene={self.scene!r} dialog={self.dialog} text=[{texts}] "
            f"suggestion={self.suggestion!r} ({self.latency_s:.1f}s)"
        )

    def to_event(self) -> dict:
        return {
            "scene": self.scene,
            "visible_text": self.visible_text,
            "dialog": self.dialog,
            "buttons": self.buttons,
            "suggestion": self.suggestion,
            "latency_s": round(self.latency_s, 1),
        }


def _http_transport(url: str, payload: dict, timeout_s: float) -> str:
    req = urllib.request.Request(
        f"{url}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.load(resp)["message"]["content"]


def _server_reachable(url: str, timeout_s: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout_s):
            return True
    except (urllib.error.URLError, OSError):
        return False


@dataclass
class LlmScreenReader:
    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = 120.0
    min_interval_s: float = 60.0
    transport: Callable[[str, dict, float], str] = _http_transport
    _last_read_ts: float = field(default=0.0, repr=False)

    @classmethod
    def from_env(cls) -> LlmScreenReader | None:
        """Build a reader from GGGE_LLM* env vars, or None when disabled or
        the server is unreachable -- callers treat None as "no LLM", so a
        machine without ollama runs exactly as before."""
        if os.environ.get("GGGE_LLM", "").lower() in ("0", "off", "no"):
            log.info("LLM screen reading disabled via GGGE_LLM")
            return None
        url = os.environ.get("GGGE_LLM_URL", DEFAULT_URL)
        model = os.environ.get("GGGE_LLM_MODEL", DEFAULT_MODEL)
        if not _server_reachable(url):
            log.warning("LLM server %s unreachable, screen reading disabled", url)
            return None
        log.info("LLM screen reading enabled: %s @ %s", model, url)
        return cls(url=url, model=model)

    def read(self, frame: np.ndarray, force: bool = False) -> ScreenReading | None:
        """Describe one frame. Returns None on rate limit, transport failure,
        or unparseable output -- never raises into a control loop."""
        now = time.monotonic()
        if not force and now - self._last_read_ts < self.min_interval_s:
            log.debug("LLM read skipped (rate limit, %.0fs interval)", self.min_interval_s)
            return None
        self._last_read_ts = now
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": PROMPT, "images": [self._encode(frame)]}
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }
            t0 = time.monotonic()
            content = self.transport(self.url, payload, self.timeout_s)
            latency = time.monotonic() - t0
        except Exception:
            log.warning("LLM read failed, continuing without it", exc_info=True)
            return None
        return self._parse(content, latency)

    @staticmethod
    def _encode(frame: np.ndarray) -> str:
        h, w = frame.shape[:2]
        long_edge = max(h, w)
        if long_edge > MAX_EDGE:
            scale = MAX_EDGE / long_edge
            frame = cv2.resize(frame, (round(w * scale), round(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            raise ValueError("jpeg encode failed")
        return base64.b64encode(buf.tobytes()).decode()

    @staticmethod
    def _parse(content: str, latency_s: float) -> ScreenReading | None:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            log.warning("LLM returned non-JSON content: %.200s", content)
            return None
        if not isinstance(data, dict):
            log.warning("LLM returned non-object JSON: %.200s", content)
            return None

        def _strs(value) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(v) for v in value]

        return ScreenReading(
            scene=str(data.get("scene", "")),
            visible_text=_strs(data.get("visible_text")),
            dialog=bool(data.get("dialog", False)),
            buttons=_strs(data.get("buttons")),
            suggestion=str(data.get("suggestion", "")),
            latency_s=latency_s,
        )
