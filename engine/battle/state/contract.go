package state

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

func FromContract(s battle.BattleState) (Content, Values) {
	content := Content{
		Units:        make([]UnitContent, len(s.Units)),
		Terrain:      s.Terrain,
		TerrainCells: slices.Clone(s.TerrainCells),
	}
	values := Values{
		Units: make([]UnitValue, len(s.Units)),
		Phase: s.Phase,
		Turn:  s.Turn,
	}
	if s.Bounds != nil {
		content.Bounds = *s.Bounds
	}
	for index := range s.Units {
		content.Units[index], values.Units[index] = fromContractUnit(s.Units[index])
	}
	return content, values
}

func (b Battle) ToContract() battle.BattleState {
	bounds := b.Content.Bounds
	out := battle.BattleState{
		Units:        make([]battle.Unit, len(b.Content.Units)),
		Phase:        b.Values.Phase,
		Turn:         b.Values.Turn,
		Bounds:       &bounds,
		Terrain:      b.Content.Terrain,
		TerrainCells: slices.Clone(b.Content.TerrainCells),
	}
	for index, unit := range b.Units() {
		out.Units[index] = toContractUnit(unit)
	}
	return out
}

func fromContractUnit(u battle.Unit) (UnitContent, UnitValue) {
	mech, pilot := fromContractMech(u.Mech), fromContractPilot(u.Pilot)
	content := UnitContent{
		Faction:                 u.Faction,
		Size:                    u.Size,
		MaxHP:                   u.MaxHP,
		ENMax:                   u.ENMax,
		SPMax:                   u.SPMax,
		ChanceStepsMax:          u.ChanceStepsMax,
		SupportDefendChargesMax: u.SupportDefendChargesMax,
		SupportAttackChargesMax: u.SupportAttackChargesMax,
		HasShield:               u.HasShield,
		SupportDefendWhenAttack: u.SupportDefendWhenAttack,
		Mech:                    &mech,
		Pilot:                   &pilot,
	}
	return content, UnitValue{
		Pos:                  u.Pos,
		HP:                   u.HP,
		EN:                   u.EN,
		SP:                   u.SP,
		Acted:                u.Acted,
		ChanceSteps:          u.ChanceSteps,
		SupportDefendCharges: u.SupportDefendCharges,
		SupportAttackCharges: u.SupportAttackCharges,
		Skills:               mapSlice(u.Skills, fromContractSkill),
		MapWeaponAmmo:        slices.Clone(u.MapWeaponAmmo),
		Debuffs:              slices.Clone(u.Debuffs),
	}
}

func toContractUnit(u Unit) battle.Unit {
	return battle.Unit{
		Faction:                 u.Faction,
		Pos:                     u.Value.Pos,
		Size:                    u.Size,
		HP:                      u.Value.HP,
		MaxHP:                   u.MaxHP,
		EN:                      u.Value.EN,
		ENMax:                   u.ENMax,
		SP:                      u.Value.SP,
		SPMax:                   u.SPMax,
		Pilot:                   toContractPilot(u.Pilot),
		Mech:                    toContractMech(u.Mech),
		Skills:                  mapSlice(u.Value.Skills, toContractSkill),
		Acted:                   u.Value.Acted,
		ChanceSteps:             u.Value.ChanceSteps,
		ChanceStepsMax:          u.ChanceStepsMax,
		SupportDefendCharges:    u.Value.SupportDefendCharges,
		SupportDefendChargesMax: u.SupportDefendChargesMax,
		SupportAttackCharges:    u.Value.SupportAttackCharges,
		SupportAttackChargesMax: u.SupportAttackChargesMax,
		HasShield:               u.HasShield,
		SupportDefendWhenAttack: u.SupportDefendWhenAttack,
		MapWeaponAmmo:           slices.Clone(u.Value.MapWeaponAmmo),
		Debuffs:                 slices.Clone(u.Value.Debuffs),
	}
}

func fromContractMech(m battle.Mech) def.Mech {
	return def.Mech{
		HP:         m.HP,
		EN:         m.EN,
		Attack:     m.Attack,
		Defense:    m.Defense,
		Mobility:   m.Mobility,
		MoveRange:  m.MoveRange,
		Weapons:    mapSlice(m.Weapons, fromContractWeapon),
		MapWeapons: mapSlice(m.MapWeapons, fromContractMapWeapon),
	}
}

func toContractMech(m *def.Mech) battle.Mech {
	if m == nil {
		return battle.Mech{}
	}
	return battle.Mech{
		MapWeapons: mapSlice(m.MapWeapons, toContractMapWeapon),
		Weapons:    mapSlice(m.Weapons, toContractWeapon),
		MoveRange:  m.MoveRange,
		Mobility:   m.Mobility,
		Defense:    m.Defense,
		Attack:     m.Attack,
		EN:         m.EN,
		HP:         m.HP,
	}
}

func fromContractPilot(p battle.Pilot) def.Pilot {
	return def.Pilot{
		Ranged:   p.Ranged,
		Melee:    p.Melee,
		Awaken:   p.Awaken,
		Defense:  p.Defense,
		Reaction: p.Reaction,
		SP:       p.SP,
	}
}

func toContractPilot(p *def.Pilot) battle.Pilot {
	if p == nil {
		return battle.Pilot{}
	}
	return battle.Pilot{
		SP:       p.SP,
		Reaction: p.Reaction,
		Defense:  p.Defense,
		Awaken:   p.Awaken,
		Melee:    p.Melee,
		Ranged:   p.Ranged,
	}
}

func fromContractWeapon(w battle.Weapon) def.Weapon {
	return def.Weapon{
		Name:            w.Name,
		Power:           w.Power,
		RangeMin:        w.RangeMin,
		RangeMax:        w.RangeMax,
		ENCost:          w.ENCost,
		Accuracy:        w.Accuracy,
		UsableAfterMove: w.UsableAfterMove,
		DebuffKind:      w.DebuffKind,
		DebuffMagnitude: w.DebuffMagnitude,
		Categories:      w.Categories,
	}
}

func toContractWeapon(w def.Weapon) battle.Weapon {
	return battle.Weapon{
		Categories:      w.Categories,
		DebuffMagnitude: w.DebuffMagnitude,
		DebuffKind:      w.DebuffKind,
		UsableAfterMove: w.UsableAfterMove,
		Accuracy:        w.Accuracy,
		ENCost:          w.ENCost,
		RangeMax:        w.RangeMax,
		RangeMin:        w.RangeMin,
		Power:           w.Power,
		Name:            w.Name,
	}
}

func fromContractMapWeapon(w battle.MapWeapon) def.MapWeapon {
	return def.MapWeapon{
		Name:            w.Name,
		Power:           w.Power,
		AffectArea:      fromContractAffectArea(w.AffectArea),
		AmmoMax:         w.AmmoMax,
		ENCost:          w.ENCost,
		Accuracy:        w.Accuracy,
		Affects:         w.Affects,
		UsableAfterMove: w.UsableAfterMove,
		DebuffKind:      w.DebuffKind,
		DebuffMagnitude: w.DebuffMagnitude,
		Categories:      w.Categories,
	}
}

func toContractMapWeapon(w def.MapWeapon) battle.MapWeapon {
	return battle.MapWeapon{
		Categories:      w.Categories,
		DebuffMagnitude: w.DebuffMagnitude,
		DebuffKind:      w.DebuffKind,
		UsableAfterMove: w.UsableAfterMove,
		Affects:         w.Affects,
		Accuracy:        w.Accuracy,
		ENCost:          w.ENCost,
		AmmoMax:         w.AmmoMax,
		AffectArea:      toContractAffectArea(w.AffectArea),
		Power:           w.Power,
		Name:            w.Name,
	}
}

func fromContractSkill(s battle.Skill) def.Skill {
	return def.Skill{
		Kind:            s.Kind,
		Source:          s.Source,
		Amount:          battle.CloneAmount(s.Amount),
		Uses:            s.Uses,
		EndsActivation:  s.EndsActivation,
		UsableAfterMove: s.UsableAfterMove,
		AffectArea:      fromContractAffectArea(s.AffectArea),
		Affects:         s.Affects,
	}
}

func toContractSkill(s def.Skill) battle.Skill {
	return battle.Skill{
		Affects:         s.Affects,
		AffectArea:      toContractAffectArea(s.AffectArea),
		UsableAfterMove: s.UsableAfterMove,
		EndsActivation:  s.EndsActivation,
		Uses:            s.Uses,
		Amount:          battle.CloneAmount(s.Amount),
		Source:          s.Source,
		Kind:            s.Kind,
	}
}

func fromContractAffectArea(a battle.AffectArea) def.AffectArea {
	return def.AffectArea{
		ApplyShape:  fromContractShape(a.ApplyShape),
		EffectShape: fromContractShape(a.EffectShape),
	}
}

func toContractAffectArea(a def.AffectArea) battle.AffectArea {
	return battle.AffectArea{
		EffectShape: ToContractShape(a.EffectShape),
		ApplyShape:  ToContractShape(a.ApplyShape),
	}
}

func fromContractShape(s battle.ShapeRange) def.ShapeRange {
	return def.ShapeRange{
		Cells:     s.Cells,
		Direction: s.Direction,
	}
}

func ToContractShape(s def.ShapeRange) battle.ShapeRange {
	return battle.ShapeRange{
		Direction: s.Direction,
		Cells:     slices.Clone(s.Cells),
	}
}

func mapSlice[In, Out any](in []In, transform func(In) Out) []Out {
	if in == nil {
		return nil
	}
	out := make([]Out, len(in))
	for index, item := range in {
		out[index] = transform(item)
	}
	return out
}
