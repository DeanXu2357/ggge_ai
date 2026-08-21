"""名冊採集幀 → sandbox-scenario/1：離線解析組裝層，不碰實機。

輸入是一個 run 目錄（sweep.jsonl＋frames/），輸出是同一個目錄下的
scenario.json 與 intel_report.json。整層只讀檔案，跑幾次結果都一樣。

三條線各自獨立，錯了也各自留在報告裡：

- 數值走字模 CV（runtime.panels／glyphs），自由文字走轉錄（panel_text 的
  PanelTranscriber）。轉錄結果一律以字串保存：武裝效果句不解析成 debuff 欄、
  能力詞條不映射成 skills／has_shield，所以 unit_intel_from_panels 永遠收到
  abilities=None——結構欄寧可留 gap 也不從詞條猜。
- 身分對位鍵是 (HP, EN)＋陣營，名字不進身分。同一組 (HP, EN) 的敵方共用一份
  情報樣板，組內哪一台站哪一格無從分辨，就標 group_assigned 說出來。
- 對帳失敗一律進報告，不拋例外也不擅自配對：台數不合、盤面多出來的格、名冊
  多出來的台、UNSURE 格全部逐筆列出。字模已知錯型（開頭多插 1、8↔9）只產生
  「近似對」提示欄位，永不自動配。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import cv2

from ..runtime import panels, sweep
from ..runtime.glyphs import Region, crop
from ..runtime.panel_text import PanelTranscriber, StageBrief, WeaponText
from ..sandbox import scenario as scenario_mod
from ..engine.contract import Faction
from .intel import Intelligence, Side, UnitIntel
from .intel_panels import PICKS, unit_intel_from_panels

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STAGE_TRUTH_ROOT = PROJECT_ROOT / "assets" / "stage_truth"

JOURNAL_NAME = "sweep.jsonl"
SCENARIO_NAME = "scenario.json"
INVALID_SCENARIO_NAME = "scenario.invalid.json"
REPORT_NAME = "intel_report.json"

DEFAULT_COLS = 25
DEFAULT_ROWS = 20
DEFAULT_BOARD_SOURCE = "default_25x20"

BASIC_PAGE = "basic"
STATS_PAGES = ("stats0", "stats1", "stats2")
WEAPON_PAGES = ("weapons", "weapons_more")
ABILITIES_PAGE = "abilities"
# 詳情頁實際只有三個分頁（stats0／weapons／abilities，見 roster_capture.DETAIL_TAB_PAGES）；
# stats1/2 與 weapons_more 是「有就吃」的加頁，缺了不算漏。
EXPECTED_PAGES = (BASIC_PAGE, "stats0", "weapons", ABILITIES_PAGE)

ENEMY = "enemy"
ALLY = "ally"
NPC = "npc"
NPC_FACTIONS = (NPC, "third_party")

EXACT = "exact"
GROUP_ASSIGNED = "group_assigned"
ARBITRARY = "arbitrary"
OBSERVED_ONLY = "observed_only"
ASSUMED_DEFAULT = "assumed_default"

STAGE_INFO_LABEL = "stage_info"


@dataclass(frozen=True)
class UnitCapture:
    """一台機體的採集結果：每一頁指到哪張幀，哪幾頁採失敗。"""

    faction: str
    index: int
    pages: dict[str, str] = field(default_factory=dict)
    failures: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ParsedUnit:
    faction: str
    index: int
    record: UnitIntel
    gaps: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    ability_lines: tuple[str, ...] = ()
    abilities_pending: bool = True
    weapon_notes: tuple[str, ...] = ()
    weapon_names_pending: tuple[int, ...] = ()
    missing_pages: tuple[str, ...] = ()
    unreadable_pages: tuple[str, ...] = ()
    capture_failures: tuple[tuple[str, str], ...] = ()

    @property
    def key(self) -> tuple[int, int]:
        return (self.record.max_hp, self.record.en_max)


@dataclass(frozen=True)
class CellFact:
    cell: tuple[int, int]
    verdict: str
    hp: int | None = None
    en: int | None = None
    sig: str | None = None


@dataclass(frozen=True)
class BoardFacts:
    cells: tuple[CellFact, ...] = ()
    source: str = "verdict_replay"

    def of(self, verdict: str) -> tuple[CellFact, ...]:
        return tuple(fact for fact in self.cells if fact.verdict == verdict)

    @property
    def enemy_cells(self) -> tuple[CellFact, ...]:
        return self.of(sweep.ENEMY)

    @property
    def ally_cells(self) -> tuple[CellFact, ...]:
        return self.of(sweep.ALLY)

    @property
    def npc_cells(self) -> tuple[CellFact, ...]:
        return self.of(sweep.NPC)

    @property
    def unsure_cells(self) -> tuple[CellFact, ...]:
        return self.of(sweep.UNSURE)


@dataclass(frozen=True)
class Deployment:
    uid: str
    intel_id: str
    faction: str
    cell: tuple[int, int]
    hp: int | None = None
    en: int | None = None
    assignment: str = EXACT


@dataclass
class Reconciliation:
    intel: Intelligence = field(default_factory=Intelligence)
    deployments: list[Deployment] = field(default_factory=list)
    parsed: tuple[ParsedUnit, ...] = ()
    facts: BoardFacts = field(default_factory=BoardFacts)
    groups: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    near_misses: list[dict[str, Any]] = field(default_factory=list)


class _Uid:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.count = 0

    def next(self) -> str:
        self.count += 1
        return f"{self.prefix}{self.count}"


def read_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def collect_captures(entries: list[dict[str, Any]]) -> list[UnitCapture]:
    """roster_capture 事件聚合成每台一筆 page→frame。同頁重採以最後一筆為準。"""
    pages: dict[tuple[str, int], dict[str, str]] = {}
    failures: dict[tuple[str, int], list[tuple[str, str]]] = {}
    order: list[tuple[str, int]] = []
    for entry in entries:
        if entry.get("kind") != "roster_capture":
            continue
        index = entry.get("index")
        if index is None:
            continue
        key = (str(entry.get("faction") or "unknown"), int(index))
        if key not in pages:
            pages[key] = {}
            failures[key] = []
            order.append(key)
        page = str(entry.get("page") or entry.get("panel_kind") or "")
        if not page:
            continue
        frame = entry.get("frame")
        if entry.get("ok") and frame:
            pages[key][page] = str(frame)
        else:
            failures[key].append((page, str(entry.get("reason") or "not_ok")))
    return [
        UnitCapture(faction=key[0], index=key[1], pages=pages[key], failures=tuple(failures[key]))
        for key in order
    ]


def list_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.get("kind") != "roster_list_end":
            continue
        count = entry.get("count")
        if count is not None:
            counts[str(entry.get("faction") or "unknown")] = int(count)
    return counts


def pick_for(weapon_rows) -> str | None:
    """POWER 最高那把武裝的類別徽章決定駕駛員攻擊挑哪一欄；沒有徽章就不挑。"""
    best = None
    for row in weapon_rows:
        if row.power is None:
            continue
        if best is None or row.power > best.power:
            best = row
    if best is None:
        return None
    for name in PICKS:
        if name in best.categories:
            return name
    return None


def _text_region(row) -> Region:
    """武裝名＋效果句合成一塊裁切，抄 scripts/parse_panel.py 的做法。"""
    region = row.name_region
    if row.note_region is None:
        return region
    return (
        region[0],
        region[1],
        region[2],
        row.note_region[1] + row.note_region[3] - region[1],
    )


def _row_key(row) -> tuple:
    return (
        row.categories,
        row.level,
        row.range_min,
        row.range_max,
        row.map_weapon,
        row.power,
        row.en_cost,
        row.hit_pct,
        row.crit_pct,
        row.ammo,
    )


def _weapon_cards(frames: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """weapons 與 weapons_more 兩頁的卡片接起來。

    clipped 的卡只露半張，數值不可信，直接丟；剩下的用數值列去重——捲動後的
    那一頁本來就會再帶出前一頁看過的卡。"""
    cards: list[tuple[str, Any]] = []
    seen: set[tuple] = set()
    for page in WEAPON_PAGES:
        frame = frames.get(page)
        if frame is None:
            continue
        for row in panels.read_weapon_rows(frame):
            if row.clipped:
                continue
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            cards.append((page, row))
    return tuple((page, replace(row, index=index)) for index, (page, row) in enumerate(cards))


def _best_column(frames: dict[str, Any]) -> panels.StatColumn | None:
    """哪一個詳情分頁的數值欄讀得最完整就用哪一個。

    能力分頁的同一欄印的是能力加成差值不是數值，讀出來的 slot 會標 delta；
    以「真的是數值」的欄位數排序，那一頁自然排不到前面。"""
    best: panels.StatColumn | None = None
    best_score = -1
    for page in (*STATS_PAGES, *WEAPON_PAGES):
        frame = frames.get(page)
        if frame is None:
            continue
        column = panels.read_stat_column(frame)
        if column is None:
            continue
        score = sum(1 for _, slot in column.slots() if slot.absolute is not None)
        if score > best_score:
            best, best_score = column, score
    return best


def _basic_view(frames: dict[str, Any]) -> panels.BasicView | None:
    frame = frames.get(BASIC_PAGE)
    return None if frame is None else panels.read_basic_view(frame)


def _weapon_texts(
    frames: dict[str, Any],
    cards: tuple[tuple[str, Any], ...],
    reader: PanelTranscriber | None,
) -> tuple[tuple[tuple[Any, WeaponText | None], ...], tuple[str, ...], tuple[int, ...]]:
    pairs: list[tuple[Any, WeaponText | None]] = []
    notes: list[str] = []
    pending: list[int] = []
    for page, row in cards:
        text = None
        lines = None
        if reader is not None:
            lines = reader.weapon_lines(crop(frames[page], _text_region(row)))
        if lines:
            # 名字空字串會讓 weapon_intel 靜靜用 weapon_N 卻不記 gap，所以只有
            # 真的轉錄到東西才給 WeaponText。
            text = WeaponText(name=lines[0])
            note = " ".join(lines[1:]).strip()
            if note:
                notes.append(f"weapon{row.index}: {note}")
        else:
            pending.append(row.index)
        pairs.append((row, text))
    return tuple(pairs), tuple(notes), tuple(pending)


def parse_unit(
    cap: UnitCapture, run_dir: Path, reader: PanelTranscriber | None = None
) -> ParsedUnit:
    """一台機體的所有頁面 → 一份 UnitIntel＋逐項缺漏。讀不到就記 gap，不猜值。"""
    run_dir = Path(run_dir)
    frames: dict[str, Any] = {}
    unreadable: list[str] = []
    for page, relative in cap.pages.items():
        image = cv2.imread(str(run_dir / relative))
        if image is None:
            unreadable.append(page)
        else:
            frames[page] = image

    cards = _weapon_cards(frames)
    rows = tuple(row for _, row in cards)
    weapons, notes, names_pending = _weapon_texts(frames, cards, reader)

    lines: tuple[str, ...] | None = None
    if reader is not None and ABILITIES_PAGE in frames:
        lines = reader.ability_lines(crop(frames[ABILITIES_PAGE], panels.CONTENT_REGION))

    # abilities=None 是刻意的：詞條只當文字保存，結構欄（skills／has_shield／
    # 攔截減輕）不從詞條推，寧可讓 gaps 誠實記一筆 abilities。
    assembled = unit_intel_from_panels(
        f"{cap.faction}_{cap.index}",
        column=_best_column(frames),
        basic=_basic_view(frames),
        weapons=weapons,
        abilities=None,
        pick=pick_for(rows),
    )
    return ParsedUnit(
        faction=cap.faction,
        index=cap.index,
        record=assembled.record,
        gaps=assembled.gaps,
        unsupported=assembled.unsupported,
        ability_lines=lines or (),
        abilities_pending=lines is None,
        weapon_notes=notes,
        weapon_names_pending=names_pending,
        missing_pages=tuple(page for page in EXPECTED_PAGES if page not in frames),
        unreadable_pages=tuple(unreadable),
        capture_failures=cap.failures,
    )


def _cell_of(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None


def _int_of(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def sweep_facts(entries: list[dict[str, Any]]) -> BoardFacts:
    """掃描裁決重放成盤面事實：同一格後筆覆蓋前筆。

    ledger_dump 在的時候，最終格集合以它為準（帳本才是那一輪的收束結果）；
    hp／en 仍從 verdict 事件取，因為 dump 只記裁決不記數值。覆蓋時新筆沒帶
    的數值沿用舊筆——出卡讀到的 HP/EN 是證據，被後來一筆沒帶數值的裁決洗掉
    等於丟證據。"""
    latest: dict[tuple[int, int], CellFact] = {}
    dump: dict[str, Any] | None = None
    for entry in entries:
        kind = entry.get("kind")
        if kind == "ledger_dump":
            dump = entry
            continue
        if kind != "verdict":
            continue
        cell = _cell_of(entry.get("cell"))
        if cell is None:
            continue
        previous = latest.get(cell)
        hp = _int_of(entry.get("hp"))
        en = _int_of(entry.get("en"))
        sig = entry.get("sig")
        latest[cell] = CellFact(
            cell=cell,
            verdict=str(entry.get("verdict") or sweep.UNSURE),
            hp=hp if hp is not None else (previous.hp if previous else None),
            en=en if en is not None else (previous.en if previous else None),
            sig=str(sig) if sig else (previous.sig if previous else None),
        )

    if dump is None:
        return BoardFacts(tuple(latest[cell] for cell in sorted(latest)), "verdict_replay")

    cells: dict[tuple[int, int], CellFact] = {}
    for raw in dump.get("cells", ()):
        cell = _cell_of(raw)
        if cell is None or not isinstance(raw, (list, tuple)) or len(raw) < 3:
            continue
        seen = latest.get(cell)
        cells[cell] = CellFact(
            cell=cell,
            verdict=str(raw[2]),
            hp=seen.hp if seen else None,
            en=seen.en if seen else None,
            sig=seen.sig if seen else None,
        )
    return BoardFacts(tuple(cells[cell] for cell in sorted(cells)), "ledger_dump")


def _differences(template: ParsedUnit, others: list[ParsedUnit]) -> list[dict[str, Any]]:
    """同組（HP,EN）相同但其他欄位不同的那幾台：照樣共用樣板，差異寫進報告。"""
    out: list[dict[str, Any]] = []
    base = template.record
    for other in others:
        fields = [
            name
            for name in UnitIntel.__dataclass_fields__
            if name != "unit_id" and getattr(base, name) != getattr(other.record, name)
        ]
        if fields:
            out.append({"index": other.index, "differs": fields})
    return out


def _variants(value: int | None) -> tuple[int, ...]:
    """已知字模錯型的還原候選：開頭多插 1、8↔9。只拿來提示，不拿來配對。"""
    if value is None:
        return ()
    text = str(value)
    out = {value, int("1" + text)}
    if text.startswith("1") and len(text) > 1:
        out.add(int(text[1:]))
    for position, char in enumerate(text):
        if char in "89":
            out.add(int(text[:position] + ("9" if char == "8" else "8") + text[position + 1 :]))
    return tuple(sorted(out))


def _near_miss(fact: CellFact, keys: list[tuple[int, int]]) -> list[str]:
    hits = []
    hps = set(_variants(fact.hp))
    ens = set(_variants(fact.en))
    for key in keys:
        if key[0] in hps and key[1] in ens:
            hits.append(f"enemy_hp{key[0]}_en{key[1]}")
    return hits


def _observed_record(intel_id: str, fact: CellFact) -> UnitIntel:
    return UnitIntel(intel_id, max_hp=fact.hp or 1, en_max=fact.en or 0)


def _observe_cell(
    recon: Reconciliation,
    fact: CellFact,
    intel_id: str,
    faction: Faction,
    side: Side,
    uid: _Uid,
) -> None:
    """名冊裡沒有這一台：用盤面看得到的 HP/EN 合成最小情報，盤面才不缺人。"""
    recon.intel.assume(_observed_record(intel_id, fact), side)
    recon.deployments.append(
        Deployment(
            uid=uid.next(),
            intel_id=intel_id,
            faction=faction.value,
            cell=fact.cell,
            hp=fact.hp,
            en=fact.en,
            assignment=OBSERVED_ONLY,
        )
    )


def _reconcile_enemy(
    recon: Reconciliation, units: list[ParsedUnit], cells: tuple[CellFact, ...]
) -> None:
    groups: dict[tuple[int, int], list[ParsedUnit]] = {}
    for unit in units:
        groups.setdefault(unit.key, []).append(unit)

    uid = _Uid("e")
    used: set[tuple[int, int]] = set()
    for key in sorted(groups):
        members = groups[key]
        intel_id = f"enemy_hp{key[0]}_en{key[1]}"
        recon.intel.assume(replace(members[0].record, unit_id=intel_id), Side.STAGE)
        matched = [
            fact for fact in cells if (fact.hp, fact.en) == key and fact.cell not in used
        ]
        recon.groups.append(
            {
                "intel_id": intel_id,
                "faction": ENEMY,
                "template_index": members[0].index,
                "members": [unit.index for unit in members],
                "cells": [list(fact.cell) for fact in matched],
                "differences": _differences(members[0], members[1:]),
            }
        )
        pairs = min(len(members), len(matched))
        assignment = EXACT if len(members) == 1 and len(matched) == 1 else GROUP_ASSIGNED
        for fact in matched[:pairs]:
            used.add(fact.cell)
            recon.deployments.append(
                Deployment(
                    uid=uid.next(),
                    intel_id=intel_id,
                    faction=Faction.ENEMY.value,
                    cell=fact.cell,
                    hp=fact.hp,
                    en=fact.en,
                    assignment=assignment,
                )
            )
        if len(members) != len(matched):
            recon.issues.append(
                {
                    "kind": "count_mismatch",
                    "faction": ENEMY,
                    "intel_id": intel_id,
                    "intel_units": len(members),
                    "board_cells": len(matched),
                }
            )
        if len(members) > pairs:
            recon.issues.append(
                {
                    "kind": "unmatched_intel",
                    "faction": ENEMY,
                    "intel_id": intel_id,
                    "units": [unit.index for unit in members[pairs:]],
                }
            )

    spare = _Uid("e_extra")
    keys = sorted(groups)
    for fact in cells:
        if fact.cell in used:
            continue
        intel_id = f"enemy_unmatched_{spare.count + 1}"
        recon.issues.append(
            {
                "kind": "unmatched_cell",
                "faction": ENEMY,
                "cell": list(fact.cell),
                "hp": fact.hp,
                "en": fact.en,
                "intel_id": intel_id,
            }
        )
        near = _near_miss(fact, keys)
        if near:
            recon.near_misses.append(
                {
                    "cell": list(fact.cell),
                    "observed": [fact.hp, fact.en],
                    "near": near,
                    "shapes": ["leading_one", "eight_nine"],
                }
            )
        _observe_cell(recon, fact, intel_id, Faction.ENEMY, Side.STAGE, spare)


def _reconcile_independent(
    recon: Reconciliation,
    units: list[ParsedUnit],
    cells: tuple[CellFact, ...],
    *,
    faction: Faction,
    side: Side,
    prefix: str,
    uid_prefix: str,
    observed_issue: str,
) -> None:
    """我方／NPC：每台自己一份樣板，(HP,EN) 精確相等才算對上。

    盤面沒讀到 HP/EN，或同一組數值有兩台以上，就退回任意指派並標明——這條路
    上「哪一台站哪一格」本來就沒有證人。"""
    catalogue: list[tuple[str, tuple[int, int]]] = []
    for unit in units:
        intel_id = f"{prefix}_{unit.index}"
        recon.intel.assume(replace(unit.record, unit_id=intel_id), side)
        catalogue.append((intel_id, unit.key))

    uid = _Uid(uid_prefix)
    remaining = list(catalogue)
    deferred: list[CellFact] = []
    for fact in cells:
        key = (fact.hp, fact.en)
        same = [item for item in remaining if item[1] == key] if None not in key else []
        if not same:
            deferred.append(fact)
            continue
        chosen = same[0]
        remaining.remove(chosen)
        unique = sum(1 for item in catalogue if item[1] == key) == 1
        crowded = sum(1 for other in cells if (other.hp, other.en) == key) > 1
        recon.deployments.append(
            Deployment(
                uid=uid.next(),
                intel_id=chosen[0],
                faction=faction.value,
                cell=fact.cell,
                hp=fact.hp,
                en=fact.en,
                assignment=EXACT if unique and not crowded else ARBITRARY,
            )
        )

    spare = _Uid(f"{uid_prefix}_extra")
    for fact in deferred:
        if remaining:
            chosen = remaining.pop(0)
            recon.deployments.append(
                Deployment(
                    uid=uid.next(),
                    intel_id=chosen[0],
                    faction=faction.value,
                    cell=fact.cell,
                    hp=fact.hp,
                    en=fact.en,
                    assignment=ARBITRARY,
                )
            )
            recon.issues.append(
                {
                    "kind": "arbitrary_assignment",
                    "faction": faction.value,
                    "cell": list(fact.cell),
                    "hp": fact.hp,
                    "en": fact.en,
                    "intel_id": chosen[0],
                }
            )
            continue
        intel_id = f"{prefix}_observed_{spare.count + 1}"
        recon.issues.append(
            {
                "kind": observed_issue,
                "faction": faction.value,
                "cell": list(fact.cell),
                "hp": fact.hp,
                "en": fact.en,
                "intel_id": intel_id,
            }
        )
        _observe_cell(recon, fact, intel_id, faction, side, spare)

    if len(catalogue) != len(cells):
        recon.issues.append(
            {
                "kind": "count_mismatch",
                "faction": faction.value,
                "intel_units": len(catalogue),
                "board_cells": len(cells),
            }
        )
    for intel_id, _ in remaining:
        recon.issues.append(
            {"kind": "unmatched_intel", "faction": faction.value, "intel_id": intel_id}
        )


def reconcile(parsed: list[ParsedUnit], facts: BoardFacts) -> Reconciliation:
    recon = Reconciliation(parsed=tuple(parsed), facts=facts)
    _reconcile_enemy(recon, [unit for unit in parsed if unit.faction == ENEMY], facts.enemy_cells)
    _reconcile_independent(
        recon,
        [unit for unit in parsed if unit.faction == ALLY],
        facts.ally_cells,
        faction=Faction.ALLY,
        side=Side.ROSTER,
        prefix=ALLY,
        uid_prefix="a",
        observed_issue="ally_observed_only",
    )
    _reconcile_independent(
        recon,
        [unit for unit in parsed if unit.faction in NPC_FACTIONS],
        facts.npc_cells,
        faction=Faction.THIRD_PARTY,
        side=Side.STAGE,
        prefix=NPC,
        uid_prefix="n",
        observed_issue="npc_observed_only",
    )
    for fact in facts.unsure_cells:
        recon.issues.append({"kind": "unsure_cell", "cell": list(fact.cell)})
    return recon


def build_intel(recon: Reconciliation) -> dict[str, Any]:
    return recon.intel.to_dict()


def build_scenario(
    recon: Reconciliation,
    stage: str,
    board: dict[str, int],
    brief: StageBrief | None = None,
    note_extra: str = "",
) -> dict[str, Any]:
    notes = []
    if brief is not None and brief.victory:
        notes.append(f"勝利條件（畫面轉錄）：{brief.victory}")
    if brief is not None and brief.defeat:
        notes.append(f"敗北條件（畫面轉錄）：{brief.defeat}")
    if note_extra:
        notes.append(note_extra)
    return {
        "format": scenario_mod.FORMAT,
        "stage": stage,
        "note": "；".join(notes),
        "board": {"cols": int(board["cols"]), "rows": int(board["rows"])},
        "rules": {},
        "intel": build_intel(recon),
        "deployment": [
            {
                "uid": item.uid,
                "intel_id": item.intel_id,
                "faction": item.faction,
                "cell": list(item.cell),
                "hp": item.hp,
                "en": item.en,
                "assignment": item.assignment,
            }
            for item in recon.deployments
        ],
        "victory": {"type": scenario_mod.VICTORY_ANNIHILATION, "source": ASSUMED_DEFAULT},
        "defeat": {"type": scenario_mod.DEFEAT_ALLY_ANNIHILATION, "source": ASSUMED_DEFAULT},
    }


def build_report(
    recon: Reconciliation,
    *,
    run: str = "",
    stage: str = "",
    board: dict[str, int] | None = None,
    board_source: str = "",
    brief: StageBrief | None = None,
    brief_pending: bool = True,
    captures: list[UnitCapture] | None = None,
    counts: dict[str, int] | None = None,
    validation_error: str | None = None,
) -> dict[str, Any]:
    return {
        "run": run,
        "stage": stage,
        "board": board or {},
        "board_source": board_source,
        "stage_brief": {
            "victory": "" if brief is None else brief.victory,
            "defeat": "" if brief is None else brief.defeat,
            "pending": brief_pending,
        },
        "board_facts_source": recon.facts.source,
        "list_counts": counts or {},
        "captures": [
            {
                "faction": cap.faction,
                "index": cap.index,
                "pages": sorted(cap.pages),
                "failures": [list(item) for item in cap.failures],
            }
            for cap in (captures or [])
        ],
        "units": [
            {
                "faction": unit.faction,
                "index": unit.index,
                "max_hp": unit.record.max_hp,
                "en_max": unit.record.en_max,
                "gaps": list(unit.gaps),
                "unsupported": list(unit.unsupported),
                "abilities_pending": unit.abilities_pending,
                "ability_lines": list(unit.ability_lines),
                "weapon_notes": list(unit.weapon_notes),
                "weapon_names_pending": list(unit.weapon_names_pending),
                "missing_pages": list(unit.missing_pages),
                "unreadable_pages": list(unit.unreadable_pages),
                "capture_failures": [list(item) for item in unit.capture_failures],
            }
            for unit in recon.parsed
        ],
        "groups": recon.groups,
        "deployments": [
            {
                "uid": item.uid,
                "intel_id": item.intel_id,
                "faction": item.faction,
                "cell": list(item.cell),
                "assignment": item.assignment,
            }
            for item in recon.deployments
        ],
        "issues": recon.issues,
        "near_misses": recon.near_misses,
        "validation_error": validation_error,
    }


def read_stage_brief(
    entries: list[dict[str, Any]], run_dir: Path, reader: PanelTranscriber | None
) -> tuple[StageBrief | None, bool]:
    """關卡資訊畫面的勝敗條件轉錄。end 幀優先——start 幀可能還在轉場。"""
    frames = [
        str(entry.get("frame"))
        for entry in entries
        if entry.get("kind") == "frame"
        and STAGE_INFO_LABEL in str(entry.get("label") or "")
        and entry.get("frame")
    ]
    ends = [
        str(entry.get("frame"))
        for entry in entries
        if entry.get("kind") == "frame"
        and str(entry.get("label") or "").endswith(":end")
        and STAGE_INFO_LABEL in str(entry.get("label") or "")
        and entry.get("frame")
    ]
    candidates = ends or frames
    if reader is None or not candidates:
        return None, True
    image = cv2.imread(str(Path(run_dir) / candidates[-1]))
    if image is None:
        return None, True
    brief = reader.stage_brief(image)
    return brief, brief is None


def load_stage_truth(
    entries: list[dict[str, Any]], root: Path = STAGE_TRUTH_ROOT
) -> dict[str, Any] | None:
    stage = None
    for entry in entries:
        if entry.get("kind") == "stage_truth" and entry.get("stage"):
            stage = str(entry["stage"])
    if stage is None:
        return None
    path = root / f"{stage}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def stage_and_board(
    entries: list[dict[str, Any]], stage_truth: dict[str, Any] | None
) -> tuple[str, dict[str, int], str]:
    stage = ""
    for entry in entries:
        if entry.get("kind") == "stage_truth" and entry.get("stage"):
            stage = str(entry["stage"])
    if stage_truth is None:
        return stage, {"cols": DEFAULT_COLS, "rows": DEFAULT_ROWS}, DEFAULT_BOARD_SOURCE
    stage = str(stage_truth.get("stage") or stage)
    raw = stage_truth.get("board") or {}
    cols, rows = raw.get("cols"), raw.get("rows")
    if not cols or not rows:
        return stage, {"cols": DEFAULT_COLS, "rows": DEFAULT_ROWS}, DEFAULT_BOARD_SOURCE
    return stage, {"cols": int(cols), "rows": int(rows)}, "stage_truth"


def run_offline(
    run_dir: Path,
    *,
    reader: PanelTranscriber | None = None,
    stage_truth: dict[str, Any] | None = None,
) -> int:
    run_dir = Path(run_dir)
    entries = read_entries(run_dir / JOURNAL_NAME)
    captures = collect_captures(entries)
    parsed = [parse_unit(cap, run_dir, reader) for cap in captures]
    facts = sweep_facts(entries)
    recon = reconcile(parsed, facts)
    brief, brief_pending = read_stage_brief(entries, run_dir, reader)
    truth = stage_truth if stage_truth is not None else load_stage_truth(entries)
    stage, board, board_source = stage_and_board(entries, truth)

    scenario = build_scenario(recon, stage, board, brief, f"generated from run {run_dir.name}")
    text = json.dumps(scenario, ensure_ascii=False, indent=2)

    error = None
    try:
        scenario_mod.from_dict(json.loads(text)).build()
    except Exception as exc:
        # 組裝失敗不准中斷這一趟：報告才是這一層的產物，壞掉的情境檔改名留證。
        error = f"{type(exc).__name__}: {exc}"
        log.warning("scenario validation failed: %s", error)

    target = run_dir / (SCENARIO_NAME if error is None else INVALID_SCENARIO_NAME)
    target.write_text(text + "\n", encoding="utf-8")
    report = build_report(
        recon,
        run=run_dir.name,
        stage=stage,
        board=board,
        board_source=board_source,
        brief=brief,
        brief_pending=brief_pending,
        captures=captures,
        counts=list_counts(entries),
        validation_error=error,
    )
    (run_dir / REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if error is None else 1
