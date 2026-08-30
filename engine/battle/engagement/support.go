package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type supportAttacker struct {
	Unit   *state.Unit
	Weapon *def.Weapon
}

// The supported unit stands on 'at' after its move, so the reach of a
// support unit reads that cell and not the cell of today.
func supportDefenders(board *state.Board, supported *state.Unit, at state.Footprint) []*state.Unit {
	out := []*state.Unit{}
	for _, other := range byFaction(board, supported.Faction) {
		if inSupportReach(other, supported, at, other.SupportDefendCharges) {
			out = append(out, other)
		}
	}
	return out
}

func supportAttackers(board *state.Board, supported *state.Unit, firing, foe state.Footprint) []supportAttacker {
	out := []supportAttacker{}
	for _, other := range byFaction(board, supported.Faction) {
		if weapon := supportWeapon(other, supported, firing, foe); weapon != nil {
			out = append(out, supportAttacker{Unit: other, Weapon: weapon})
		}
	}
	return out
}

func supportWeapon(other, supported *state.Unit, firing, foe state.Footprint) *def.Weapon {
	if !inSupportReach(other, supported, firing, other.SupportAttackCharges) {
		return nil
	}
	distance := geometry.Distance(other.Footprint, foe)
	for index := range other.Mech.Weapons {
		weapon := &other.Mech.Weapons[index]
		if !weapon.MapWeapon && hasENFor(other, *weapon) && weapon.Range.Holds(distance) {
			return weapon
		}
	}
	return nil
}

func inSupportReach(other, supported *state.Unit, at state.Footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		geometry.Distance(other.Footprint, at) <= other.Mech.MoveRange
}
