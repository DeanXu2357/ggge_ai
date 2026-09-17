// Package state holds the two columns of a battle and the view that a system
// reads. The package 'engine/battle' holds the contract, and this package
// converts between the two forms.
package state

import (
	"fmt"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

type UnitContent struct {
	Faction                 battle.Faction
	Size                    battle.Cell
	MaxHP                   int
	ENMax                   int
	SPMax                   int
	ChanceStepsMax          int
	SupportDefendChargesMax int
	SupportAttackChargesMax int
	HasShield               bool
	SupportDefendWhenAttack bool
	MoveRange               int
	MPInitial               int
	Mech                    *def.Mech
	Pilot                   *def.Pilot
}

type Content struct {
	Units        []UnitContent
	Bounds       battle.Bounds
	Terrain      battle.Terrain
	TerrainCells []battle.TerrainCell
}

type Values struct {
	Units []UnitValue
	Phase battle.Faction
	Turn  int
}

type UnitValue struct {
	Pos                  battle.Cell
	HP                   int
	EN                   int
	SP                   int
	Acted                bool
	ChanceSteps          int
	SupportDefendCharges int
	SupportAttackCharges int
	MoveRange            int
	MP                   int
	Skills               []def.Skill
	MapWeaponAmmo        []int
	Debuffs              []battle.Debuff
	MechAbilities        []ability.Line
	PilotAbilities       []ability.Line
	Hooks                ability.Hooks // derived from the lines; rebuilt by Clone and by SetAbilities
}

// Unit is the handle of one unit: the static side and the dynamic side, no
// copy.
type Unit struct {
	*UnitContent
	Value *UnitValue
}

// Clone answers the working column of a system. It deep-copies the slices of
// each value, so a system that writes the clone never reaches the column it
// received. The definition data is shared, as everywhere.
func (v Values) Clone() Values {
	out := v
	out.Units = make([]UnitValue, len(v.Units))
	for index := range v.Units {
		out.Units[index] = copyValue(v.Units[index])
	}
	return out
}

func copyValue(value UnitValue) UnitValue {
	value.Skills = mapSlice(value.Skills, copySkill)
	value.MapWeaponAmmo = slices.Clone(value.MapWeaponAmmo)
	value.Debuffs = slices.Clone(value.Debuffs)
	value.SetAbilities(ability.CloneLines(value.MechAbilities), ability.CloneLines(value.PilotAbilities))
	return value
}

// SetAbilities takes the lines of the mech and of the pilot and binds the
// chains over both, the mech first.
func (v *UnitValue) SetAbilities(mech, pilot []ability.Line) {
	v.MechAbilities, v.PilotAbilities = mech, pilot
	v.Hooks = ability.HooksOf(slices.Concat(mech, pilot))
}

func copySkill(skill def.Skill) def.Skill {
	skill.Amount = battle.CloneAmount(skill.Amount)
	return skill
}

// A lookup that finds nothing answers with a handle that holds a nil Value, so
// this method tolerates a nil Value.
func (u Unit) Alive() bool {
	return u.Value != nil && u.Value.HP > 0
}

// This method does not lift a size of zero to one, and the contract method
// does. The size of a unit that enters here is already one or more:
// 'board.validate' lifts it before the conversion runs.
func (u Unit) Footprint() battle.Footprint {
	return battle.Footprint{Anchor: u.Value.Pos, Size: u.Size}
}

func (u Unit) WeaponAt(id int) (*def.Weapon, error) {
	if u.Mech == nil || id < 0 || id >= len(u.Mech.Weapons) {
		return nil, fmt.Errorf("%w: the unit carries no weapon %d", battle.ErrIllegalAction, id)
	}
	return &u.Mech.Weapons[id], nil
}

func (u Unit) MapWeaponAt(id int) (*def.MapWeapon, error) {
	if u.Mech == nil || id < 0 || id >= len(u.Mech.MapWeapons) {
		return nil, fmt.Errorf("%w: the unit carries no map weapon %d", battle.ErrIllegalAction, id)
	}
	return &u.Mech.MapWeapons[id], nil
}

// PhaseIndex counts the phases from the first phase of the first turn. A
// debuff carries the index of the phase that applied it.
func (v *Values) PhaseIndex() int {
	for index, faction := range battle.PhaseOrder {
		if faction == v.Phase {
			return v.Turn*len(battle.PhaseOrder) + index
		}
	}
	return v.Turn * len(battle.PhaseOrder)
}
