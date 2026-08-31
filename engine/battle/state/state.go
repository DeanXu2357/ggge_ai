// Package state holds the battle that the systems read and write. The package
// 'engine/battle' holds the contract, and 'engine/battle/board' converts
// between the two.
package state

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

type Unit struct {
	ID                      string
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
	Ammo                 map[string]int
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

func (b *Battle) Unit(id string) *Unit {
	for index := range b.Units {
		if b.Units[index].ID == id {
			return &b.Units[index]
		}
	}
	return nil
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
