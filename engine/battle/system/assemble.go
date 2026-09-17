package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type Origin int

const (
	Fresh Origin = iota
	Resumed
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

	for index := range candidate.Units {
		var err error
		switch origin {
		case Fresh:
			err = openNewBattle(index, &candidate.Units[index])
		case Resumed:
			values := state.Values{Phase: candidate.Phase, Turn: candidate.Turn}
			err = resumeBattle(index, &candidate.Units[index], values.PhaseIndex())
		}
		if err != nil {
			return state.Content{}, state.Values{}, err
		}
	}

	content, values := state.FromContract(candidate)
	assembleContent(&content, &values)
	return content, values, nil
}

// The contract object carries no move range value yet, so both origins take
// the value from the maximum.
func assembleContent(content *state.Content, values *state.Values) {
	for index := range content.Units {
		content.Units[index].MoveRange = content.Units[index].Mech.MoveRange
		values.Units[index].MoveRange = content.Units[index].MoveRange
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
	if u.MaxHP <= 0 {
		return fmt.Errorf("%w: unit %d carries the maximum HP %d", battle.ErrOutsideContract, index, u.MaxHP)
	}
	if u.ENMax <= 0 {
		return fmt.Errorf("%w: unit %d carries the maximum EN %d", battle.ErrOutsideContract, index, u.ENMax)
	}
	if u.SPMax <= 0 {
		return fmt.Errorf("%w: unit %d carries the maximum SP %d", battle.ErrOutsideContract, index, u.SPMax)
	}
	return nil
}

func openNewBattle(index int, u *battle.Unit) error {
	stated := map[string]bool{
		"hp": u.HP != 0, "en": u.EN != 0, "sp": u.SP != 0, "acted": u.Acted,
		"chance_steps":           u.ChanceSteps != 0,
		"support_attack_charges": u.SupportAttackCharges != 0,
		"support_defend_charges": u.SupportDefendCharges != 0,
		"map_weapon_ammo":        len(u.MapWeaponAmmo) != 0, "debuffs": len(u.Debuffs) != 0,
	}
	for _, field := range []string{"hp", "en", "sp", "acted", "chance_steps",
		"support_attack_charges", "support_defend_charges", "map_weapon_ammo", "debuffs"} {
		if stated[field] {
			return fmt.Errorf("%w: unit %d states %q on a fresh battle", battle.ErrOutsideContract, index, field)
		}
	}
	u.HP, u.EN, u.SP = u.MaxHP, u.ENMax, u.SPMax
	u.ChanceSteps = u.ChanceStepsMax
	u.SupportAttackCharges, u.SupportDefendCharges = u.SupportAttackChargesMax, u.SupportDefendChargesMax
	u.MapWeaponAmmo = make([]int, len(u.Mech.MapWeapons))
	for i, weapon := range u.Mech.MapWeapons {
		u.MapWeaponAmmo[i] = weapon.AmmoMax
	}
	u.Debuffs = []battle.Debuff{}
	return nil
}

func resumeBattle(index int, u *battle.Unit, now int) error {
	for _, v := range []struct {
		name       string
		value, max int
	}{
		{"hp", u.HP, u.MaxHP}, {"en", u.EN, u.ENMax}, {"sp", u.SP, u.SPMax},
		{"chance_steps", u.ChanceSteps, u.ChanceStepsMax},
		{"support_attack_charges", u.SupportAttackCharges, u.SupportAttackChargesMax},
		{"support_defend_charges", u.SupportDefendCharges, u.SupportDefendChargesMax},
	} {
		if v.value < 0 || v.value > v.max {
			return fmt.Errorf("%w: unit %d carries %s %d outside 0..%d", battle.ErrOutsideContract, index, v.name, v.value, v.max)
		}
	}
	if len(u.MapWeaponAmmo) != len(u.Mech.MapWeapons) {
		return fmt.Errorf("%w: unit %d carries %d ammunition counts and %d map weapons", battle.ErrOutsideContract,
			index, len(u.MapWeaponAmmo), len(u.Mech.MapWeapons))
	}
	for i, ammo := range u.MapWeaponAmmo {
		if ammo < 0 || ammo > u.Mech.MapWeapons[i].AmmoMax {
			return fmt.Errorf("%w: unit %d carries the ammunition %d of the map weapon %d outside 0..%d", battle.ErrOutsideContract,
				index, ammo, i, u.Mech.MapWeapons[i].AmmoMax)
		}
	}
	for _, debuff := range u.Debuffs {
		if debuff.AppliedPhase > now {
			return fmt.Errorf("%w: unit %d carries a debuff applied at the phase %d, after the phase %d", battle.ErrOutsideContract,
				index, debuff.AppliedPhase, now)
		}
	}
	return nil
}
