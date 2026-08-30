package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
)

type supportAttacker struct {
	Unit   *battle.Unit
	Weapon *battle.Weapon
}

// The supported unit stands on 'at' after its move, so the reach of a
// support unit reads that cell and not the cell of today.
func supportDefenders(board *battle.BattleState, supported *battle.Unit, at battle.Footprint) []*battle.Unit {
	out := []*battle.Unit{}
	for _, other := range byFaction(board, supported.Faction) {
		if inSupportReach(other, supported, at, other.SupportDefendCharges) {
			out = append(out, other)
		}
	}
	return out
}

func supportAttackers(board *battle.BattleState, supported *battle.Unit, firing, foe battle.Footprint) []supportAttacker {
	out := []supportAttacker{}
	for _, other := range byFaction(board, supported.Faction) {
		if weapon := supportWeapon(other, supported, firing, foe); weapon != nil {
			out = append(out, supportAttacker{Unit: other, Weapon: weapon})
		}
	}
	return out
}

func supportWeapon(other, supported *battle.Unit, firing, foe battle.Footprint) *battle.Weapon {
	if !inSupportReach(other, supported, firing, other.SupportAttackCharges) {
		return nil
	}
	distance := geometry.Distance(other.Footprint(), foe)
	for index := range other.Mech.Weapons {
		weapon := &other.Mech.Weapons[index]
		if fires(other, weapon, distance) {
			return weapon
		}
	}
	return nil
}

func inSupportReach(other, supported *battle.Unit, at battle.Footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		geometry.Distance(other.Footprint(), at) <= other.Mech.MoveRange
}
