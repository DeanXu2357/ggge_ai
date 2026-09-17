"""情報庫：以單位識別為鍵的靜態情報，供 TacticalAdvisor 組裝沙盤輸入。

兩區——roster（我方，關卡外蒐集）與 stage（敵方，關卡內 Inspect 蒐集）。
learn 與 assume 的分界就是「畫面才是權威」那條線：learn 來自這一輪親眼
讀到的面板，記錄並標記 known；assume 來自快取或定義檔，只給資料不給
known，所以規劃仍會排 Inspect 去確認。

戰場動態（hp／en 即值、acted、debuff、支援次數餘額）永不進本庫，
一律由呼叫端逐 tick 餵。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from enum import StrEnum
from typing import Any

from ..runtime.perceive import Observation, Perceiver
from ..engine.contract import Cell, Faction
from ..engine.state import Ability, MapWeapon, Mech, Pilot, Skill, Unit, Weapon
from .state import StageState

# The SP pool of every pilot is 15 (user, first hand, 2026-09-15). The device
# panel has no SP reading, so the current SP is not observed yet.
SP_MAX = 15

FORMAT_VERSION = 1

MELEE = "melee"
SHOOTING = "shooting"
AWAKENING = "awakening"


class Side(StrEnum):
    ROSTER = "roster"
    STAGE = "stage"


@dataclass(frozen=True)
class WeaponIntel:
    """categories ＝ 面板徽章（格鬥／射擊／覺醒），一把可以掛多枚，所以是集合
    而非單值；駕駛員攻擊值挑哪一欄由它決定（UnitIntel.offence_for）。

    crit_pct 是面板原值，沙盤還沒有爆擊節點——先存不換算，接法定了再對映。
    """

    name: str
    power: float
    range_min: int = 1
    range_max: int = 1
    en_cost: int = 0
    accuracy: float = 0.0
    map_weapon: bool = False
    ammo: int = 0
    debuff_kind: str | None = None
    debuff_magnitude: float = 0.0
    categories: tuple[str, ...] = ()
    crit_pct: int = 0
    level: int = 0

    def to_weapon(self) -> Weapon:
        return Weapon(
            name=self.name,
            power=self.power,
            range_min=self.range_min,
            range_max=self.range_max,
            en_cost=self.en_cost,
            accuracy=self.accuracy,
            debuff_kind=self.debuff_kind,
            debuff_magnitude=self.debuff_magnitude,
        )

    def to_map_weapon(self) -> MapWeapon:
        # 面板讀不到地圖兵器的形狀：沒有格子、沒有朝向。兩個形狀都留空，
        # 等有形狀來源再填（issue #79）。空的 apply_shape 在契約裡代表以
        # 自機格為中心，這裡卻只是缺資料，規則不得照字面讀。
        return MapWeapon(
            name=self.name,
            power=self.power,
            ammo_max=self.ammo,
            en_cost=self.en_cost,
            accuracy=self.accuracy,
            debuff_kind=self.debuff_kind,
            debuff_magnitude=self.debuff_magnitude,
        )


@dataclass(frozen=True)
class SkillIntel:
    kind: str
    amount: float | None = None
    uses: int = 1
    ends_activation: bool = True

    def to_skill(self) -> Skill:
        # 面板讀不到技能的形狀：沒有格子、沒有朝向。兩個形狀都留空，等有形狀
        # 來源再填。空的 apply_shape 在契約裡代表以自機格為中心，這裡卻只是
        # 缺資料，規則不得照字面讀。
        return Skill(
            kind=self.kind,
            amount=self.amount,
            uses=self.uses,
            ends_activation=self.ends_activation,
        )


def allowance_lines(
    support_attack: int, support_defend: int, chance_steps: int
) -> list[Ability]:
    """The allowance lines that give a unit the allowances the panel shows.

    The engine derives the support allowances from 0 and the chance steps
    from 1 (user, 2026-09-17), so a panel allowance above the base is a line
    on the pilot.
    """
    out: list[Ability] = []
    if support_attack > 0:
        out.append(Ability(kind="support_attack_plus", plus=support_attack))
    if support_defend > 0:
        out.append(Ability(kind="support_defend_plus", plus=support_defend))
    if chance_steps > 1:
        out.append(Ability(kind="chance_step_plus", plus=chance_steps - 1))
    return out


@dataclass(frozen=True)
class UnitIntel:
    """docs/spec/intel-data-spec.md 的欄位表，扣掉戰場動態那一列。

    pilot_attack 是「已挑好的那一欄」，三欄原值另存 pilot_shooting／melee／
    awakening——遊戲把駕駛員攻擊拆三欄而沙盤 Unit 只有一欄，挑選發生在組裝
    時（decisions.md 0730）。
    """

    unit_id: str
    max_hp: int = 1
    en_max: int = 0
    unit_attack: float = 0.0
    unit_defense: float = 0.0
    pilot_attack: float = 0.0
    pilot_defense: float = 0.0
    reaction: float = 0.0
    mobility: float = 0.0
    move_range: int = 0
    weapons: tuple[WeaponIntel, ...] = ()
    skills: tuple[SkillIntel, ...] = ()
    chance_steps_max: int = 0
    support_attack_charges_max: int = 0
    support_defend_charges_max: int = 0
    has_shield: bool = False
    support_defend_when_attack: bool = False
    pilot_shooting: float = 0.0
    pilot_melee: float = 0.0
    pilot_awakening: float = 0.0
    unit_lv: int = 0
    pilot_lv: int = 0
    pilot_sp: int = 0

    def offence_for(self, weapon: WeaponIntel) -> float:
        """武裝類別對應的駕駛員攻擊值。多枚徽章取最小值——沙盤拿它算我方
        傷害，低估只會讓 KILL 判準更保守；無徽章或該欄沒讀到就退回已挑選的
        pilot_attack。"""
        values = [
            value
            for category, value in (
                (MELEE, self.pilot_melee),
                (SHOOTING, self.pilot_shooting),
                (AWAKENING, self.pilot_awakening),
            )
            if category in weapon.categories and value > 0
        ]
        return min(values) if values else self.pilot_attack

    def to_unit(
        self,
        faction: Faction,
        *,
        pos: Cell = (0, 0),
        hp: int | None = None,
        en: int | None = None,
        acted: bool = False,
        pilot_attack: float | None = None,
    ) -> Unit:
        # 三欄原值還沒進沙盤武裝：to_weapon 不寫 categories，引擎的
        # AttackFor 讀不到類別就取三欄最大值。三欄一律填已挑好的那一欄，
        # 挑選才留在組裝端，數值與改型前相同。
        attack = self.pilot_attack if pilot_attack is None else pilot_attack
        return Unit(
            faction=faction,
            pos=pos,
            hp=self.max_hp if hp is None else hp,
            en=self.en_max if en is None else en,
            move_range=self.move_range,
            pilot=Pilot(
                ranged=attack,
                melee=attack,
                awaken=attack,
                defense=self.pilot_defense,
                reaction=self.reaction,
                sp=SP_MAX,
                abilities=allowance_lines(
                    self.support_attack_charges_max,
                    self.support_defend_charges_max,
                    self.chance_steps_max,
                ),
            ),
            mech=Mech(
                hp=self.max_hp,
                en=self.en_max,
                attack=self.unit_attack,
                defense=self.unit_defense,
                mobility=self.mobility,
                move_range=self.move_range,
                weapons=[
                    weapon.to_weapon() for weapon in self.weapons if not weapon.map_weapon
                ],
                map_weapons=[
                    weapon.to_map_weapon() for weapon in self.weapons if weapon.map_weapon
                ],
            ),
            skills=[skill.to_skill() for skill in self.skills],
            acted=acted,
            chance_steps=self.chance_steps_max,
            support_defend_charges=self.support_defend_charges_max,
            support_attack_charges=self.support_attack_charges_max,
            has_shield=self.has_shield,
            support_defend_when_attack=self.support_defend_when_attack,
            map_weapon_ammo=[
                weapon.ammo for weapon in self.weapons if weapon.map_weapon
            ],
        )


@dataclass
class Intelligence:
    roster: dict[str, UnitIntel] = field(default_factory=dict)
    stage: dict[str, UnitIntel] = field(default_factory=dict)
    confirmed: set[str] = field(default_factory=set)

    def learn(self, record: UnitIntel, side: Side) -> None:
        self._section(side)[record.unit_id] = record
        self.confirmed.add(record.unit_id)

    def assume(self, record: UnitIntel, side: Side) -> None:
        self._section(side)[record.unit_id] = record

    def record(self, unit_id: str) -> UnitIntel | None:
        return self.roster.get(unit_id) or self.stage.get(unit_id)

    def known(self, unit_id: str) -> bool:
        return unit_id in self.confirmed

    def unit(
        self,
        unit_id: str,
        faction: Faction,
        *,
        pos: Cell = (0, 0),
        hp: int | None = None,
        en: int | None = None,
        acted: bool = False,
        pilot_attack: float | None = None,
    ) -> Unit | None:
        record = self.record(unit_id)
        if record is None:
            return None
        return record.to_unit(
            faction, pos=pos, hp=hp, en=en, acted=acted, pilot_attack=pilot_attack
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": FORMAT_VERSION,
            Side.ROSTER.value: {uid: asdict(rec) for uid, rec in sorted(self.roster.items())},
            Side.STAGE.value: {uid: asdict(rec) for uid, rec in sorted(self.stage.items())},
        }

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    def _section(self, side: Side) -> dict[str, UnitIntel]:
        return self.roster if side is Side.ROSTER else self.stage


def from_dict(data: dict[str, Any]) -> Intelligence:
    """讀回來的一律是先驗：檔案不是畫面，載入不給 known。"""
    return Intelligence(
        roster={uid: _record_from_dict(raw) for uid, raw in data.get(Side.ROSTER.value, {}).items()},
        stage={uid: _record_from_dict(raw) for uid, raw in data.get(Side.STAGE.value, {}).items()},
    )


def loads(text: str) -> Intelligence:
    return from_dict(json.loads(text))


def _record_from_dict(data: dict[str, Any]) -> UnitIntel:
    scalars = {key: value for key, value in data.items() if key not in ("weapons", "skills")}
    return UnitIntel(
        weapons=tuple(_weapon_from_dict(raw) for raw in data.get("weapons", ())),
        skills=tuple(_skill_from_dict(raw) for raw in data.get("skills", ())),
        **scalars,
    )


def _weapon_from_dict(data: dict[str, Any]) -> WeaponIntel:
    # json 沒有 tuple：categories 讀回來是 list，不轉回去往返比較就不相等。
    # 只讀認得的欄位：舊 dump 會帶已退役的鍵（protocol 1.4 的 can_counter）。
    known = {entry.name for entry in fields(WeaponIntel)}
    kept = {key: value for key, value in data.items() if key in known}
    return WeaponIntel(**{**kept, "categories": tuple(data.get("categories", ()))})


def _skill_from_dict(data: dict[str, Any]) -> SkillIntel:
    return SkillIntel(
        kind=str(data["kind"]),
        amount=data.get("amount"),
        uses=data.get("uses", 1),
        ends_activation=data.get("ends_activation", True),
    )


@dataclass(frozen=True)
class IntelPerceiver:
    """把情報庫的 known 併進觀測——整條感知鏈唯一承認非畫面來源的接縫。

    known 是程序內記憶，畫面上讀不出來，但規劃層要靠它才排得出 Inspect。
    收在感知裝飾器裡有三個好處：迴圈不必持有它看不到的狀態、StageState
    仍是純值、例外面只有這一處可稽核。庫只在讀過詳情面板後才 learn，
    所以 known 的推進終究仍由畫面證據驅動。
    """

    inner: Perceiver[StageState]
    intel: Intelligence

    def look(self) -> Observation[StageState]:
        seen = self.inner.look()
        state = seen.state
        if state is None:
            return seen
        known = frozenset(
            unit for unit in state.allies | state.enemies if self.intel.known(unit)
        )
        if known == state.known:
            return seen
        return replace(seen, state=replace(state, known=known))
