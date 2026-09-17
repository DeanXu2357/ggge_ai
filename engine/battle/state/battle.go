package state

import (
	"fmt"
	"iter"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

// Battle borrows the two columns of a battle and owns neither.
type Battle struct {
	Content *Content
	Values  *Values
}

// Units walks every unit of the battle with its id.
func (b Battle) Units() iter.Seq2[int, Unit] {
	return func(yield func(int, Unit) bool) {
		for index := range b.Content.Units {
			if !yield(index, b.unit(index)) {
				return
			}
		}
	}
}

func (b Battle) unit(index int) Unit {
	return Unit{UnitContent: &b.Content.Units[index], Value: &b.Values.Units[index]}
}

// UnitAt is the one door from a unit id to the data behind it.
func (b Battle) UnitAt(id int) (Unit, error) {
	if id < 0 || id >= len(b.Content.Units) {
		return Unit{}, fmt.Errorf("%w: %d", battle.ErrNoUnit, id)
	}
	return b.unit(id), nil
}

func (b Battle) ToContract() battle.BattleState {
	bounds := b.Content.Bounds
	out := battle.BattleState{
		Units:        make([]battle.Unit, len(b.Content.Units)),
		Phase:        b.Values.Phase,
		Turn:         b.Values.Turn,
		Bounds:       &bounds,
		Terrain:      b.Content.Terrain,
		TerrainCells: slices.Clone(b.Content.TerrainCells),
	}
	for index, unit := range b.Units() {
		out.Units[index] = toContractUnit(unit)
	}
	return out
}

// UnitValues answers the wire form of the value column of one unit, for the
// terminal values of an act.
func (b Battle) UnitValues(id int) battle.UnitValues {
	return toContractValues(b.unit(id).Value)
}
