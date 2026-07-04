from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..perception.base import Bbox, ScreenId
from .template import Template, TemplateRecognizer, load_template

MANIFEST_NAME = "manifest.yaml"


@dataclass
class TemplateEntry:
    id: str
    file: str
    search_region: tuple[int, int, int, int] | None = None
    screen: ScreenId | None = None

    def to_dict(self) -> dict:
        data: dict = {"file": self.file}
        if self.search_region is not None:
            data["search_region"] = list(self.search_region)
        if self.screen is not None:
            data["screen"] = self.screen
        return data


@dataclass
class TemplateManifest:
    root: Path
    screens: dict[ScreenId, TemplateEntry] = field(default_factory=dict)
    elements: dict[str, TemplateEntry] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.root / MANIFEST_NAME

    @classmethod
    def load(cls, root: Path) -> TemplateManifest:
        manifest = cls(root=root)
        path = root / MANIFEST_NAME
        if not path.exists():
            return manifest
        data = yaml.safe_load(path.read_text()) or {}
        for sid, raw in (data.get("screens") or {}).items():
            manifest.screens[sid] = _entry(sid, raw)
        for eid, raw in (data.get("elements") or {}).items():
            manifest.elements[eid] = _entry(eid, raw)
        return manifest

    def save(self) -> None:
        data = {
            "screens": {sid: e.to_dict() for sid, e in sorted(self.screens.items())},
            "elements": {eid: e.to_dict() for eid, e in sorted(self.elements.items())},
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

    def build_recognizer(self) -> TemplateRecognizer:
        return TemplateRecognizer(
            screen_anchors={sid: self._load(e) for sid, e in self.screens.items()},
            element_templates={eid: self._load(e) for eid, e in self.elements.items()},
        )

    def element_ids_by_screen(self) -> dict[ScreenId, list[str]]:
        result: dict[ScreenId, list[str]] = {}
        for eid, entry in self.elements.items():
            if entry.screen is not None:
                result.setdefault(entry.screen, []).append(eid)
        return result

    def _load(self, entry: TemplateEntry) -> Template:
        region = Bbox(*entry.search_region) if entry.search_region else None
        return load_template(entry.id, self.root / entry.file, region)


def _entry(id: str, raw: dict) -> TemplateEntry:
    region = raw.get("search_region")
    return TemplateEntry(
        id=id,
        file=raw["file"],
        search_region=tuple(region) if region else None,
        screen=raw.get("screen"),
    )
