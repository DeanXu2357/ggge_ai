package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type actionKind string

const (
	actionAttack     actionKind = "attack"
	actionMapAttack  actionKind = "map_attack"
	actionReposition actionKind = "reposition"
	actionStandby    actionKind = "standby"
)

type stance string

const (
	stanceDodge   stance = "dodge"
	stanceDefend  stance = "defend"
	stanceCounter stance = "counter"
	stanceNone    stance = "none"
)

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

// decision is one activation of one unit. The contract names the payload
// 'action' and the model names it 'decision'; this package keeps the model
// name.
type decision struct {
	UnitID         string
	Kind           actionKind
	MoveTo         *state.Cell
	TargetID       string
	Weapon         string
	Amount         *float64
	Aim            *state.Cell
	ResponseAttack *responseAttack

	SupportDefender  string
	SupportAttackers []string
}

type responseAttack struct {
	Stance           stance
	Weapon           string
	SupportDefender  string
	SupportAttackers []string
}
