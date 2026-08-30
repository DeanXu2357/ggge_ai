package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
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
	MoveTo   *state.Cell
	TargetID string
	Weapon   string
	Amount   *float64
	Aim      *state.Cell
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

func alive(unit *state.Unit) bool {
	return unit != nil && unit.HP > 0
}

func hasENFor(unit *state.Unit, weapon def.Weapon) bool {
	return unit.EN >= weapon.ENCost
}

func weaponOf(unit *state.Unit, name string) *def.Weapon {
	for index := range unit.Mech.Weapons {
		if unit.Mech.Weapons[index].Name == name {
			return &unit.Mech.Weapons[index]
		}
	}
	return nil
}

func byFaction(board *state.Board, faction state.Faction) []*state.Unit {
	var out []*state.Unit
	for index := range board.Units {
		other := &board.Units[index]
		if other.Faction == faction && alive(other) {
			out = append(out, other)
		}
	}
	return out
}
