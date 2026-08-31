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

func nameOf(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

func hasENFor(unit *state.Unit, weapon def.Weapon) bool {
	return unit.Value.EN >= weapon.ENCost
}

func fires(unit *state.Unit, weapon *def.Weapon, distance int) bool {
	return weapon != nil && hasENFor(unit, *weapon) && weapon.Reaches(distance)
}

func weaponOf(unit *state.Unit, name string) *def.Weapon {
	for index := range unit.Mech.Weapons {
		if unit.Mech.Weapons[index].Name == name {
			return &unit.Mech.Weapons[index]
		}
	}
	return nil
}

func byFaction(board *state.Battle, faction battle.Faction) []*state.Unit {
	var out []*state.Unit
	for index := range board.Units {
		other := &board.Units[index]
		if other.Faction == faction && other.Alive() {
			out = append(out, other)
		}
	}
	return out
}
