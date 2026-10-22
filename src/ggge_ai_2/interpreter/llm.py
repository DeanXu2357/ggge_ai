from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

import anthropic
import cv2
from pydantic import BaseModel, ValidationError

from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.stream.contract import Frame

log = logging.getLogger(__name__)

ANSWER_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "screen": {"type": "string"},
        "auto": {"type": ["boolean", "null"]},
    },
    "required": ["reason", "screen", "auto"],
    "additionalProperties": False,
}


class Answer(BaseModel):
    reason: str
    screen: str
    auto: bool | None


@dataclass(frozen=True)
class LlmInterpreter:
    client: anthropic.Anthropic
    system: str
    model: str = "claude-haiku-5-5"
    width: int = 1170

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": self._encode(frame),
                            },
                        },
                        {
                            "type": "text",
                            "text": "Candidate screens: "
                            + ", ".join(sorted(c.value for c in candidates)),
                        },
                    ],
                }
            ],
        )
        if response.stop_reason == "refusal":
            log.warning("llm refusal", extra={"frame_seq": frame.seq})
            return None
        text = next((block.text for block in response.content if block.type == "text"), None)
        try:
            answer = None if text is None else Answer.model_validate_json(text)
        except ValidationError:
            answer = None
        if answer is None:
            log.warning(
                "llm answer unreadable",
                extra={"frame_seq": frame.seq, "stop_reason": response.stop_reason},
            )
            return None
        log.info(
            "llm answer",
            extra={
                "frame_seq": frame.seq,
                "screen": answer.screen,
                "auto": answer.auto,
                "reason": answer.reason,
                "cache_read_input_tokens": response.usage.cache_read_input_tokens,
                "input_tokens": response.usage.input_tokens,
            },
        )
        if answer.screen not in Screen:
            return None
        return Situation(frame.seq, Screen(answer.screen), answer.auto)

    def _encode(self, frame: Frame) -> str:
        h, w = frame.image.shape[:2]
        size = (self.width, round(h * self.width / w))
        small = cv2.resize(frame.image, size, interpolation=cv2.INTER_AREA)
        ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError("JPEG encoding failed")
        return base64.standard_b64encode(jpeg.tobytes()).decode()
