package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var knownStances = map[battle.Stance]bool{
	battle.StanceDodge:   true,
	battle.StanceDefend:  true,
	battle.StanceCounter: true,
	battle.StanceNone:    true,
}

// Prepare bounds-checks every id of a plan before Commit reads it, so a
// refusal here is a broken invariant of the engine and not a bad request.
func unitOf(board state.Battle, id int) state.Unit {
	unit, err := board.UnitAt(id)
	if err != nil {
		panic(err)
	}
	return unit
}

func weaponOf(unit state.Unit, id int) *def.Weapon {
	weapon, err := unit.WeaponAt(id)
	if err != nil {
		panic(err)
	}
	return weapon
}

func hasENFor(unit state.Unit, weapon def.Weapon) bool {
	return unit.Value.EN >= weapon.ENCost
}

func fires(unit state.Unit, weapon *def.Weapon, distance int) bool {
	return weapon != nil && hasENFor(unit, *weapon) && weapon.Reaches(distance)
}

func byFaction(board state.Battle, faction battle.Faction) []int {
	var out []int
	for index, other := range board.Units() {
		if other.Faction == faction && other.Alive() {
			out = append(out, index)
		}
	}
	return out
}
