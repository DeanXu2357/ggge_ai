// Package state holds the battle that the systems read and write. The package
// 'engine/battle' holds the contract, and this package converts between the
// two forms.
package state

import (
	"fmt"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
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

type Unit struct {
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
	Mech                    *def.Mech
	Pilot                   *def.Pilot
	Value                   UnitValue
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
	Skills               []def.Skill
	MapWeaponAmmo        []int
	Debuffs              []battle.Debuff
}

type Battle struct {
	Units        []Unit
	Phase        battle.Faction
	Turn         int
	Bounds       battle.Bounds
	Terrain      battle.Terrain
	TerrainCells []battle.TerrainCell
}

// Compose is the entry copy of a system. It deep-copies the slices of each
// value, so a system that writes the working form never reaches the column it
// received. The definition data is shared, as everywhere.
func Compose(content *Content, values Values) Battle {
	out := Battle{
		Units:        make([]Unit, len(content.Units)),
		Phase:        values.Phase,
		Turn:         values.Turn,
		Bounds:       content.Bounds,
		Terrain:      content.Terrain,
		TerrainCells: content.TerrainCells,
	}
	for index := range content.Units {
		out.Units[index] = composeUnit(content.Units[index], values.Units[index])
	}
	return out
}

// The working form owns its column after Compose, so the extraction moves the
// headers and copies nothing.
func (b *Battle) Column() Values {
	out := Values{Units: make([]UnitValue, len(b.Units)), Phase: b.Phase, Turn: b.Turn}
	for index := range b.Units {
		out.Units[index] = b.Units[index].Value
	}
	return out
}

func composeUnit(content UnitContent, value UnitValue) Unit {
	return Unit{
		Faction:                 content.Faction,
		Size:                    content.Size,
		MaxHP:                   content.MaxHP,
		ENMax:                   content.ENMax,
		SPMax:                   content.SPMax,
		ChanceStepsMax:          content.ChanceStepsMax,
		SupportDefendChargesMax: content.SupportDefendChargesMax,
		SupportAttackChargesMax: content.SupportAttackChargesMax,
		HasShield:               content.HasShield,
		SupportDefendWhenAttack: content.SupportDefendWhenAttack,
		Mech:                    content.Mech,
		Pilot:                   content.Pilot,
		Value:                   copyValue(value),
	}
}

func copyValue(value UnitValue) UnitValue {
	value.Skills = mapSlice(value.Skills, copySkill)
	value.MapWeaponAmmo = slices.Clone(value.MapWeaponAmmo)
	value.Debuffs = slices.Clone(value.Debuffs)
	return value
}

func copySkill(skill def.Skill) def.Skill {
	skill.Amount = battle.CloneAmount(skill.Amount)
	return skill
}

// A lookup that finds nothing answers with a nil unit, so this method
// tolerates a nil receiver.
func (u *Unit) Alive() bool {
	return u != nil && u.Value.HP > 0
}

// This method does not lift a size of zero to one, and the contract method
// does. The size of a unit that enters here is already one or more:
// 'board.validate' lifts it before the conversion runs.
func (u *Unit) Footprint() battle.Footprint {
	return battle.Footprint{Anchor: u.Value.Pos, Size: u.Size}
}

// UnitAt is the one door from a unit id to the data behind it.
func (b *Battle) UnitAt(id int) (*Unit, error) {
	if id < 0 || id >= len(b.Units) {
		return nil, fmt.Errorf("%w: %d", battle.ErrNoUnit, id)
	}
	return &b.Units[id], nil
}

func (u *Unit) WeaponAt(id int) (*def.Weapon, error) {
	if u.Mech == nil || id < 0 || id >= len(u.Mech.Weapons) {
		return nil, fmt.Errorf("%w: the unit carries no weapon %d", battle.ErrIllegalAction, id)
	}
	return &u.Mech.Weapons[id], nil
}

func (u *Unit) MapWeaponAt(id int) (*def.MapWeapon, error) {
	if u.Mech == nil || id < 0 || id >= len(u.Mech.MapWeapons) {
		return nil, fmt.Errorf("%w: the unit carries no map weapon %d", battle.ErrIllegalAction, id)
	}
	return &u.Mech.MapWeapons[id], nil
}

// PhaseIndex counts the phases from the first phase of the first turn. A
// debuff carries the index of the phase that applied it.
func (b *Battle) PhaseIndex() int {
	for index, faction := range battle.PhaseOrder {
		if faction == b.Phase {
			return b.Turn*len(battle.PhaseOrder) + index
		}
	}
	return b.Turn * len(battle.PhaseOrder)
}
