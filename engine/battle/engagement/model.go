package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var knownStances = map[battle.Stance]bool{
	battle.StanceDodge:   true,
	battle.StanceDefend:  true,
	battle.StanceCounter: true,
	battle.StanceNone:    true,
}

func nameOf(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

func hasENFor(unit *battle.Unit, weapon battle.Weapon) bool {
	return unit.EN >= weapon.ENCost
}

// A map weapon fires at an area, and the area is not in the contract, so no
// exchange reads one.
func directWeapon(weapon *battle.Weapon) bool {
	return weapon != nil && !weapon.MapWeapon
}

func fires(unit *battle.Unit, weapon *battle.Weapon, distance int) bool {
	return directWeapon(weapon) && hasENFor(unit, *weapon) && weapon.Reaches(distance)
}

func weaponOf(unit *battle.Unit, name string) *battle.Weapon {
	for index := range unit.Mech.Weapons {
		if unit.Mech.Weapons[index].Name == name {
			return &unit.Mech.Weapons[index]
		}
	}
	return nil
}

func byFaction(board *battle.BattleState, faction battle.Faction) []*battle.Unit {
	var out []*battle.Unit
	for index := range board.Units {
		other := &board.Units[index]
		if other.Faction == faction && other.Alive() {
			out = append(out, other)
		}
	}
	return out
}
