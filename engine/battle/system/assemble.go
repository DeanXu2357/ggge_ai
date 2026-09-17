package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type Origin int

const (
	Fresh Origin = iota
	Resumed
)

// The MP facts of the user (2026-09-04, first hand): the maximum is 12 and
// the initial value is 0 or 1, not settled; 0 until issue #54 settles it.
const (
	mpInitial = 0
	mpMax     = 12
)

const (
	supportChargesBase = 0
	chanceStepsBase    = 1
)

var knownFactions = map[battle.Faction]bool{
	battle.FactionAlly:       true,
	battle.FactionEnemy:      true,
	battle.FactionThirdParty: true,
}

func Assemble(candidate battle.BattleState, origin Origin) (state.Content, state.Values, error) {
	if err := validateAssemble(&candidate); err != nil {
		return state.Content{}, state.Values{}, err
	}
	content, values, err := state.FromContract(candidate)
	if err != nil {
		return state.Content{}, state.Values{}, err
	}
	assembleContent(&content, &values)

	for index := range content.Units {
		unit := state.Unit{UnitContent: &content.Units[index], Value: &values.Units[index]}
		var err error
		switch origin {
		case Fresh:
			err = openNewBattle(index, unit)
		case Resumed:
			err = resumeBattle(index, unit, values.PhaseIndex())
		}
		if err != nil {
			return state.Content{}, state.Values{}, err
		}
	}
	return content, values, nil
}

func assembleContent(content *state.Content, values *state.Values) {
	for index := range content.Units {
		unit := &content.Units[index]
		a := ability.AssembleContext{Unit: ability.Unit{Mech: unit.Mech, Pilot: unit.Pilot}}
		values.Units[index].Hooks.Assemble(&a)
		unit.MaxHP = int(scaled(float64(unit.Mech.HP), a.MaxHPPercent))
		unit.ENMax = int(scaled(float64(unit.Mech.EN), a.MaxENPercent))
		unit.SPMax = unit.Pilot.SP
		unit.MoveRange = unit.Mech.MoveRange + a.MoveRangePlus
		unit.MPInitial = min(mpMax, mpInitial+a.MPPlus)
		unit.SupportAttackChargesMax = supportChargesBase + a.SupportAttackPlus
		unit.SupportDefendChargesMax = supportChargesBase + a.SupportDefendPlus
		unit.ChanceStepsMax = chanceStepsBase + a.ChanceStepPlus
	}
}

func validateAssemble(s *battle.BattleState) error {
	if s.Bounds == nil {
		return fmt.Errorf("%w: %w: the state carries no bounds", battle.ErrOutsideContract, battle.ErrOutsideContract)
	}
	bounds := *s.Bounds
	if bounds[1][0] < bounds[0][0] || bounds[1][1] < bounds[0][1] {
		return fmt.Errorf("%w: the bounds %v run backward", battle.ErrOutsideContract, bounds)
	}
	if !knownFactions[s.Phase] {
		return fmt.Errorf("%w: the state carries the phase %q, which is not in the contract", battle.ErrOutsideContract,
			s.Phase)
	}
	for index := range s.Units {
		if err := validateUnit(index, &s.Units[index], bounds); err != nil {
			return err
		}
	}
	for _, entry := range s.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return fmt.Errorf("%w: the terrain cell %v stands outside the board", battle.ErrOutsideContract, entry.Cell)
		}
	}
	if s.Terrain == "" {
		s.Terrain = battle.TerrainSpace
	}
	return nil
}

// A base of zero is a broken payload, not a value to fill (user ruling
// 2026-09-15 on the maxima, restated for the base data on 2026-09-17).
func validateUnit(index int, u *battle.Unit, bounds battle.Bounds) error {
	if !knownFactions[u.Faction] {
		return fmt.Errorf("%w: unit %d carries the faction %q, which is not in the contract", battle.ErrOutsideContract,
			index, u.Faction)
	}
	for axis := range u.Size {
		if u.Size[axis] < 0 {
			return fmt.Errorf("%w: unit %d carries the size %v", battle.ErrOutsideContract, index, u.Size)
		}
	}
	u.Size = u.Footprint().Size
	if !u.Footprint().Within(bounds) {
		return fmt.Errorf("%w: the unit %d stands outside the board", battle.ErrOutsideContract, index)
	}
	for _, base := range []struct {
		name  string
		value int
	}{{"mech.hp", u.Mech.HP}, {"mech.en", u.Mech.EN}, {"pilot.sp", u.Pilot.SP}} {
		if base.value <= 0 {
			return fmt.Errorf("%w: unit %d carries the base %s %d", battle.ErrOutsideContract, index, base.name, base.value)
		}
	}
	return nil
}

func openNewBattle(index int, u state.Unit) error {
	v := u.Value
	stated := map[string]bool{
		"hp": v.HP != 0, "en": v.EN != 0, "sp": v.SP != 0, "mp": v.MP != 0, "move_range": v.MoveRange != 0,
		"acted":                  v.Acted,
		"chance_steps":           v.ChanceSteps != 0,
		"support_attack_charges": v.SupportAttackCharges != 0,
		"support_defend_charges": v.SupportDefendCharges != 0,
		"map_weapon_ammo":        len(v.MapWeaponAmmo) != 0, "debuffs": len(v.Debuffs) != 0,
	}
	for _, field := range []string{"hp", "en", "sp", "mp", "move_range", "acted", "chance_steps",
		"support_attack_charges", "support_defend_charges", "map_weapon_ammo", "debuffs"} {
		if stated[field] {
			return fmt.Errorf("%w: unit %d states %q on a fresh battle", battle.ErrOutsideContract, index, field)
		}
	}
	v.HP, v.EN, v.SP, v.MP, v.MoveRange = u.MaxHP, u.ENMax, u.SPMax, u.MPInitial, u.MoveRange
	v.ChanceSteps = u.ChanceStepsMax
	v.SupportAttackCharges, v.SupportDefendCharges = u.SupportAttackChargesMax, u.SupportDefendChargesMax
	v.MapWeaponAmmo = make([]int, len(u.Mech.MapWeapons))
	for i, weapon := range u.Mech.MapWeapons {
		v.MapWeaponAmmo[i] = weapon.AmmoMax
	}
	v.Debuffs = []battle.Debuff{}
	return nil
}

// A value is judged against the maximum the assembly derived, never against
// one the payload states: a payload that a rule of another version wrote
// is refused here.
func resumeBattle(index int, u state.Unit, now int) error {
	v := u.Value
	for _, one := range []struct {
		name       string
		value, max int
	}{
		{"hp", v.HP, u.MaxHP}, {"en", v.EN, u.ENMax}, {"sp", v.SP, u.SPMax}, {"mp", v.MP, mpMax},
		{"move_range", v.MoveRange, u.MoveRange},
		{"chance_steps", v.ChanceSteps, u.ChanceStepsMax},
		{"support_attack_charges", v.SupportAttackCharges, u.SupportAttackChargesMax},
		{"support_defend_charges", v.SupportDefendCharges, u.SupportDefendChargesMax},
	} {
		if one.value < 0 || one.value > one.max {
			return fmt.Errorf("%w: unit %d carries %s %d outside 0..%d", battle.ErrOutsideContract, index, one.name, one.value, one.max)
		}
	}
	if len(v.MapWeaponAmmo) != len(u.Mech.MapWeapons) {
		return fmt.Errorf("%w: unit %d carries %d ammunition counts and %d map weapons", battle.ErrOutsideContract,
			index, len(v.MapWeaponAmmo), len(u.Mech.MapWeapons))
	}
	for i, ammo := range v.MapWeaponAmmo {
		if ammo < 0 || ammo > u.Mech.MapWeapons[i].AmmoMax {
			return fmt.Errorf("%w: unit %d carries the ammunition %d of the map weapon %d outside 0..%d", battle.ErrOutsideContract,
				index, ammo, i, u.Mech.MapWeapons[i].AmmoMax)
		}
	}
	for _, debuff := range v.Debuffs {
		if debuff.AppliedPhase > now {
			return fmt.Errorf("%w: unit %d carries a debuff applied at the phase %d, after the phase %d", battle.ErrOutsideContract,
				index, debuff.AppliedPhase, now)
		}
	}
	return nil
}
