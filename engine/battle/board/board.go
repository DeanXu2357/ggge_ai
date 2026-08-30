package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state state.Board
}

func newBoard(bounds state.Bounds, units []state.Unit) (*Board, error) {
	if bounds.High[0] < bounds.Low[0] || bounds.High[1] < bounds.Low[1] {
		return nil, fmt.Errorf("the bounds %v run backward", bounds)
	}
	seen := make(map[string]bool, len(units))
	for index := range units {
		id := units[index].ID
		if seen[id] {
			return nil, fmt.Errorf("the board holds two units with the id %q", id)
		}
		seen[id] = true
	}
	return &Board{state: state.Board{Bounds: bounds, Units: units}}, nil
}

func (b *Board) terrainAt(cell state.Cell) state.Terrain {
	if kind, declared := b.state.TerrainCells[cell]; declared {
		return kind
	}
	return b.state.DefaultTerrain
}

func (b *Board) terrainOf(unit *state.Unit) state.Terrain {
	if unit == nil {
		return b.state.DefaultTerrain
	}
	return b.terrainAt(unit.Footprint.Anchor)
}

var phaseOrder = [...]state.Faction{state.FactionAlly, state.FactionThirdParty, state.FactionEnemy}

func (b *Board) phaseIndex() int {
	for index, faction := range phaseOrder {
		if faction == b.state.Phase {
			return b.state.Turn*len(phaseOrder) + index
		}
	}
	return b.state.Turn * len(phaseOrder)
}

func (b *Board) unit(id string) *state.Unit {
	return b.state.Unit(id)
}

// The command 'act' reads this gate; the reporting commands do not, because
// a report of a unit that acted is still the answer to the question.
func (b *Board) activatable(unitID string) (*state.Unit, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return nil, err
	}
	if unit.Faction != b.state.Phase {
		return nil, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			battle.ErrOffPhase, unitID, unit.Faction, b.state.Phase)
	}
	if unit.Acted {
		return nil, fmt.Errorf("%w: %q", battle.ErrActed, unitID)
	}
	return unit, nil
}

func (b *Board) livingUnit(id string) (*state.Unit, error) {
	unit := b.unit(id)
	if unit == nil {
		return nil, fmt.Errorf("%w: %q", battle.ErrNoUnit, id)
	}
	if !alive(unit) {
		return nil, fmt.Errorf("%w: %q", battle.ErrDestroyed, id)
	}
	return unit, nil
}

func (b *Board) ReachableCells(unitID string) ([]protocol.Cell, error) {
	cells, err := b.reachableCells(unitID)
	if err != nil {
		return nil, err
	}
	return encodeCells(cells), nil
}

func (b *Board) reachableCells(unitID string) ([]state.Cell, error) {
	unit := b.unit(unitID)
	if unit == nil {
		return nil, fmt.Errorf("the board holds no unit %q", unitID)
	}
	return sortedCells(b.reachableAnchors(unit)), nil
}

func (b *Board) reachableAnchors(unit *state.Unit) cellSet {
	return reachableAnchors(unit.Footprint, unit.Mech.MoveRange,
		b.blockingCells(unit), b.occupiedCells(unit), b.state.Bounds)
}

func (b *Board) byFaction(faction state.Faction) []*state.Unit {
	var out []*state.Unit
	for index := range b.state.Units {
		other := &b.state.Units[index]
		if other.Faction == faction && alive(other) {
			out = append(out, other)
		}
	}
	return out
}

func (b *Board) targetsOf(unit *state.Unit) []*state.Unit {
	return b.byFaction(unit.Faction.Opposing())
}

func (b *Board) blockingCells(unit *state.Unit) cellSet {
	out := cellSet{}
	for index := range b.state.Units {
		other := &b.state.Units[index]
		if other.ID == unit.ID || !alive(other) || other.Faction == unit.Faction {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}

func (b *Board) occupiedCells(unit *state.Unit) cellSet {
	out := cellSet{}
	for index := range b.state.Units {
		other := &b.state.Units[index]
		if other.ID == unit.ID || !alive(other) {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}
