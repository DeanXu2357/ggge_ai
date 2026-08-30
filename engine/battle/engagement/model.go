package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

type ActionKind string

const (
	ActionAttack     ActionKind = "attack"
	ActionMapAttack  ActionKind = "map_attack"
	ActionReposition ActionKind = "reposition"
	ActionStandby    ActionKind = "standby"
)

type Stance string

const (
	StanceDodge   Stance = "dodge"
	StanceDefend  Stance = "defend"
	StanceCounter Stance = "counter"
	StanceNone    Stance = "none"
)

var knownStances = map[Stance]bool{
	StanceDodge:   true,
	StanceDefend:  true,
	StanceCounter: true,
	StanceNone:    true,
}

// Decision is one activation of one unit. The contract names the payload
// 'action' and the model names it 'decision'; this package keeps the model
// name.
type Decision struct {
	UnitID   string
	Kind     ActionKind
	MoveTo   *battle.Cell
	TargetID string
	Weapon   string
	Amount   *float64
	Aim      *battle.Cell
	Response *Response

	SupportDefender  string
	SupportAttackers []string
}

type Response struct {
	Stance           Stance
	Weapon           string
	SupportDefender  string
	SupportAttackers []string
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
