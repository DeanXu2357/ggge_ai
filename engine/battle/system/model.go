package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func weaponOf(unit unit, id int) *def.Weapon {
	weapon, err := unit.WeaponAt(id)
	if err != nil {
		panic(err)
	}
	return weapon
}

func enCostOf(shooter unit, part ability.Part, weapon *def.Weapon) int {
	w := ability.WeaponCostContext{Shooter: shooter.toAbilityUnit(part), Weapon: weapon}
	shooter.Value.Hooks.WeaponCost(&w)
	return int(scaled(float64(weapon.ENCost), w.ENCostPercent))
}

func hasENFor(unit unit, part ability.Part, weapon *def.Weapon) bool {
	return unit.Value.EN >= enCostOf(unit, part, weapon)
}

func canFire(shooter unit, part ability.Part, weapon *def.Weapon, distance int) error {
	if !hasENFor(shooter, part, weapon) {
		return fmt.Errorf("%w: unit %d cannot pay for the weapon %q",
			battle.ErrIllegalAction, shooter.id, weapon.Name)
	}
	if !weapon.Reaches(distance) {
		return fmt.Errorf("%w: the weapon %q of unit %d does not reach",
			battle.ErrIllegalAction, weapon.Name, shooter.id)
	}
	return nil
}

func byFaction(board state.Battle, faction battle.Faction) []int {
	var out []int
	for index, other := range units(board) {
		if other.Faction == faction && other.Alive() {
			out = append(out, index)
		}
	}
	return out
}
