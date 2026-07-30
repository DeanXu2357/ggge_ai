"""Free-text panel fields via a local vision LLM, bound to a closed schema.

Numbers never come through here -- runtime.glyphs owns those. What is left is
CJK prose: weapon names, weapon effect lines, ability wording. The channel is
constrained on two independent axes so a hallucination cannot reach the
sandbox:

- **schema closure.** The request carries a JSON schema whose enums list only
  mechanics the sandbox actually implements (sandbox.model's Weapon.debuff_kind,
  Skill.kind, and the Unit ability flags). ollama constrains decoding to it,
  while coerce_weapon/coerce_abilities re-check every field afterwards, because
  a schema the server ignored is not a guarantee. Wording that does not land in
  an enum is reported under `unsupported` with the verbatim excerpt: it is not
  guessed at, not widened, and not fed to the sandbox. Supporting a new
  mechanic is a code change to the sandbox and to these enums, in that order.
  The schema also shrinks to what the panel can actually answer: a weapon card
  with no effect line is asked for a name only.
- **vocabulary alignment.** Names are matched against a transcribed term list
  and only accepted when they land on one exactly or within a single character
  of exactly one entry. Anything else is kept verbatim with matched=False.

Tests inject a fake reader or a fake transport; nothing here requires ollama to
be running, and OllamaPanelTextReader.from_env returns None when it is not.

Measured 2026-07-30 on the kshatriya weapons fixture: gemma3:27b transcribed
none of the three names correctly and answered in Simplified Chinese. The
guards held (every name came back matched=False) but the channel is not yet
usable for names; model choice is still open.
"""

from __future__ import annotations

import base64
import functools
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

log = logging.getLogger(__name__)

VOCABULARY_PATH = (
    Path(__file__).resolve().parents[3] / "assets" / "catalog" / "panel_terms.json"
)

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:27b"
MAX_EDGE = 1280
JPEG_QUALITY = 92
MIN_ALIGN_LEN = 3

DAMAGE_TAKEN_UP = "damage_taken_up"
SHIELD_DEFENSE = "shield_defense"
ATTACK_SHIELD = "attack_shield"
INTERCEPTION_REDUCTION = "interception_reduction"
SUPPORT_DEFEND_CHARGE = "support_defend_charge"

WEAPON_EFFECTS: tuple[str, ...] = (DAMAGE_TAKEN_UP,)
ABILITY_EFFECTS: tuple[str, ...] = (
    SHIELD_DEFENSE,
    ATTACK_SHIELD,
    INTERCEPTION_REDUCTION,
    SUPPORT_DEFEND_CHARGE,
)
SKILL_KINDS: tuple[str, ...] = ("skill_en_refill", "skill_heal")
OWNERS: tuple[str, ...] = ("unit", "pilot")

WEAPON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "effect", "magnitude", "unsupported"],
    "properties": {
        "name": {"type": "string"},
        "effect": {"type": ["string", "null"], "enum": [*WEAPON_EFFECTS, None]},
        "magnitude": {"type": "number"},
        "unsupported": {"type": "array", "items": {"type": "string"}},
    },
}

WEAPON_NAME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
}

ABILITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entries", "unsupported"],
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "owner", "effect", "magnitude"],
                "properties": {
                    "name": {"type": "string"},
                    "owner": {"type": "string", "enum": list(OWNERS)},
                    "effect": {
                        "type": ["string", "null"],
                        "enum": [*ABILITY_EFFECTS, *SKILL_KINDS, None],
                    },
                    "magnitude": {"type": "number"},
                },
            },
        },
        "unsupported": {"type": "array", "items": {"type": "string"}},
    },
}

WEAPON_NAME_PROMPT = (
    "This crop is one weapon row from a Traditional Chinese mobile game panel. "
    "Transcribe the weapon name on the top line verbatim, in Traditional "
    "Chinese exactly as printed. Do not translate it, do not convert it to "
    "Simplified Chinese, and do not guess a plausible weapon name."
)

WEAPON_PROMPT = (
    WEAPON_NAME_PROMPT
    + " Below the name is one effect sentence. Map it to one of the listed "
    "effect codes and put its percentage in magnitude as a fraction "
    "(10% -> 0.1). damage_taken_up means only this: the struck target will "
    "take MORE damage from later attacks. A sentence that lowers the target's "
    "own attack power, raises your own power, or changes hit or critical rates "
    "is NOT damage_taken_up. For anything that is not damage_taken_up, set "
    "effect to null and copy the sentence verbatim into unsupported. Never "
    "invent an effect code."
)

ABILITY_PROMPT = (
    "This crop lists ability entries from a Traditional Chinese mobile game "
    "panel. Each entry has an icon, a name with a level suffix, and a "
    "description. Transcribe each name verbatim without the level. owner is "
    "'unit' for machine abilities and 'pilot' for pilot abilities. Map each "
    "description to one of the listed effect codes with its percentage in "
    "magnitude as a fraction (20% -> 0.2): shield_defense is a shield that "
    "reduces damage when defending, attack_shield is intercepting an attack "
    "aimed at an ally, interception_reduction reduces the interception "
    "penalty, support_defend_charge grants extra support-defend uses, "
    "skill_en_refill restores EN, skill_heal restores HP. For any other "
    "description set effect to null and copy the description into unsupported. "
    "Never invent an effect code."
)


@dataclass(frozen=True)
class WeaponText:
    name: str
    matched: bool = False
    effect: str | None = None
    magnitude: float = 0.0
    unsupported: tuple[str, ...] = ()


@dataclass(frozen=True)
class AbilityText:
    name: str
    owner: str
    matched: bool = False
    effect: str | None = None
    magnitude: float = 0.0


@dataclass(frozen=True)
class AbilityTexts:
    entries: tuple[AbilityText, ...] = ()
    unsupported: tuple[str, ...] = ()


class PanelTextReader(Protocol):
    """The seam every caller depends on; production and fakes both satisfy it."""

    def weapon(self, patch: np.ndarray, *, has_note: bool = True) -> WeaponText | None: ...

    def abilities(self, patch: np.ndarray) -> AbilityTexts | None: ...


@functools.cache
def vocabulary() -> dict[str, tuple[str, ...]]:
    """Transcribed panel terms, grouped by field. Missing file means no
    alignment, not a failure: every name then stays verbatim."""
    try:
        raw = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("panel vocabulary unavailable at %s", VOCABULARY_PATH)
        return {}
    return {key: tuple(values) for key, values in raw.items() if isinstance(values, list)}


def _normalise(text: str) -> str:
    return "".join(text.split()).replace("　", "").upper()


def _distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 1:
        return 2
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def align(text: str, terms: Iterable[str]) -> tuple[str, bool]:
    """Snap `text` onto the term list, or keep it verbatim.

    A single-character miss is corrected only when exactly one term is that
    close; ties and larger misses stay verbatim so nothing is invented. Names
    below MIN_ALIGN_LEN are never corrected -- one character out of two is not
    a typo, it is a different word.
    """
    stripped = text.strip()
    if not stripped:
        return "", False
    wanted = _normalise(stripped)
    candidates = list(terms)
    for term in candidates:
        if _normalise(term) == wanted:
            return term, True
    if len(wanted) < MIN_ALIGN_LEN:
        return stripped, False
    near = [term for term in candidates if _distance(_normalise(term), wanted) <= 1]
    if len(near) == 1:
        return near[0], True
    return stripped, False


def _enum(value: Any, allowed: Sequence[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def coerce_weapon(data: Any, terms: Iterable[str] = ()) -> WeaponText | None:
    """Re-check a weapon reply against the closed schema. Off-enum effects are
    demoted to unsupported rather than dropped silently."""
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", "")).strip()
    if not name:
        return None
    aligned, matched = align(name, terms)
    effect = _enum(data.get("effect"), WEAPON_EFFECTS)
    unsupported = _strings(data.get("unsupported"))
    raw_effect = data.get("effect")
    if effect is None and isinstance(raw_effect, str) and raw_effect.strip():
        unsupported = unsupported + (f"effect={raw_effect}",)
    return WeaponText(
        name=aligned,
        matched=matched,
        effect=effect,
        magnitude=_number(data.get("magnitude")) if effect else 0.0,
        unsupported=unsupported,
    )


def coerce_abilities(data: Any, terms: Iterable[str] = ()) -> AbilityTexts | None:
    if not isinstance(data, dict):
        return None
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        return None
    terms = tuple(terms)
    entries: list[AbilityText] = []
    unsupported = list(_strings(data.get("unsupported")))
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        owner = _enum(raw.get("owner"), OWNERS)
        if owner is None:
            unsupported.append(f"owner={raw.get('owner')} name={name}")
            continue
        aligned, matched = align(name, terms)
        effect = _enum(raw.get("effect"), (*ABILITY_EFFECTS, *SKILL_KINDS))
        raw_effect = raw.get("effect")
        if effect is None and isinstance(raw_effect, str) and raw_effect.strip():
            unsupported.append(f"effect={raw_effect} name={name}")
        entries.append(
            AbilityText(
                name=aligned,
                owner=owner,
                matched=matched,
                effect=effect,
                magnitude=_number(raw.get("magnitude")) if effect else 0.0,
            )
        )
    return AbilityTexts(entries=tuple(entries), unsupported=tuple(unsupported))


def _http_transport(url: str, payload: dict, timeout_s: float) -> str:
    request = urllib.request.Request(
        f"{url}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.load(response)["message"]["content"]


def _server_reachable(url: str, timeout_s: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout_s):
            return True
    except (urllib.error.URLError, OSError):
        return False


def encode(patch: np.ndarray) -> str:
    height, width = patch.shape[:2]
    edge = max(height, width)
    if edge > MAX_EDGE:
        scale = MAX_EDGE / edge
        patch = cv2.resize(patch, (round(width * scale), round(height * scale)))
    ok, buffer = cv2.imencode(".jpg", patch, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("jpeg encode failed")
    return base64.b64encode(buffer.tobytes()).decode()


@dataclass
class OllamaPanelTextReader:
    """ollama-backed reader. `transport` is the injection seam for tests."""

    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = 180.0
    transport: Callable[[str, dict, float], str] = _http_transport
    terms: dict[str, tuple[str, ...]] = field(default_factory=vocabulary)

    @classmethod
    def from_env(cls) -> OllamaPanelTextReader | None:
        if os.environ.get("GGGE_LLM", "").lower() in ("0", "off", "no"):
            return None
        url = os.environ.get("GGGE_LLM_URL", DEFAULT_URL)
        model = os.environ.get("GGGE_PANEL_LLM_MODEL", DEFAULT_MODEL)
        if not _server_reachable(url):
            log.warning("panel text LLM unreachable at %s", url)
            return None
        return cls(url=url, model=model)

    def weapon(self, patch: np.ndarray, *, has_note: bool = True) -> WeaponText | None:
        """has_note=False drops the effect fields from the schema entirely.

        Whether a card carries an effect line is already known deterministically
        (panels._note_region), and leaving effect in the schema for a card that
        has none invites the model to fill it: gemma3:27b asserted
        damage_taken_up on all three kshatriya weapons, two of which print no
        sentence at all.
        """
        if has_note:
            data = self._ask(patch, WEAPON_PROMPT, WEAPON_SCHEMA)
        else:
            data = self._ask(patch, WEAPON_NAME_PROMPT, WEAPON_NAME_SCHEMA)
        return coerce_weapon(data, self.terms.get("weapons", ()))

    def abilities(self, patch: np.ndarray) -> AbilityTexts | None:
        data = self._ask(patch, ABILITY_PROMPT, ABILITY_SCHEMA)
        return coerce_abilities(data, self.terms.get("abilities", ()))

    def _ask(self, patch: np.ndarray, prompt: str, schema: dict) -> Any:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": [encode(patch)]}],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
        }
        try:
            return json.loads(self.transport(self.url, payload, self.timeout_s))
        except Exception:
            log.warning("panel text read failed, continuing without it", exc_info=True)
            return None
