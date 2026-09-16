package system

import (
	"fmt"
	"iter"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// unit is one unit as the systems read it, composed from the two columns.
// 'state.Unit' is the form of the boundary alone: 'toStateUnit' makes it for the
// callers of the package.
type unit struct {
	id int
	*state.UnitContent
	Value *state.UnitValue
}

func findUnit(board state.Battle, id int) (unit, error) {
	if id < 0 || id >= len(board.Content.Units) {
		return unit{}, fmt.Errorf("%w: %d", battle.ErrNoUnit, id)
	}
	return unitOf(board, id), nil
}

func unitOf(board state.Battle, id int) unit {
	return unit{id: id, UnitContent: &board.Content.Units[id], Value: &board.Values.Units[id]}
}

func units(board state.Battle) iter.Seq2[int, unit] {
	return func(yield func(int, unit) bool) {
		for index := range board.Content.Units {
			if !yield(index, unitOf(board, index)) {
				return
			}
		}
	}
}

func (u unit) toStateUnit() state.Unit {
	return state.Unit{UnitContent: u.UnitContent, Value: u.Value}
}

// A lookup that finds nothing answers a unit that holds a nil Value, so this
// method tolerates a nil Value.
func (u unit) Alive() bool {
	return u.Value != nil && u.Value.HP > 0
}

func (u unit) Footprint() battle.Footprint {
	return u.footprintAt(u.Value.Pos)
}

// The size of a unit that enters here is already one or more:
// 'board.validate' lifts a zero before the conversion runs.
func (u unit) footprintAt(anchor battle.Cell) battle.Footprint {
	return battle.Footprint{Anchor: anchor, Size: u.Size}
}

func (u unit) WeaponAt(id int) (*def.Weapon, error) {
	if u.Mech == nil || id < 0 || id >= len(u.Mech.Weapons) {
		return nil, fmt.Errorf("%w: the unit carries no weapon %d", battle.ErrIllegalAction, id)
	}
	return &u.Mech.Weapons[id], nil
}

func (u unit) MapWeaponAt(id int) (*def.MapWeapon, error) {
	if u.Mech == nil || id < 0 || id >= len(u.Mech.MapWeapons) {
		return nil, fmt.Errorf("%w: the unit carries no map weapon %d", battle.ErrIllegalAction, id)
	}
	return &u.Mech.MapWeapons[id], nil
}

func (u unit) toAbilityUnit(part ability.Part) ability.Unit {
	return ability.Unit{Mech: u.Mech, Pilot: u.Pilot, HP: u.Value.HP, MaxHP: u.MaxHP,
		Debuffs: u.Value.Debuffs, Part: part}
}
