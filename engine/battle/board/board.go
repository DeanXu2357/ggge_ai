package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	bounds         bounds
	units          []unit
	phase          faction
	turn           int
	defaultTerrain terrain
	terrainCells   map[cell]terrain
}

func newBoard(bounds bounds, units []unit) (*Board, error) {
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
	return &Board{bounds: bounds, units: units}, nil
}

func (b *Board) terrainAt(cell cell) terrain {
	if kind, declared := b.terrainCells[cell]; declared {
		return kind
	}
	return b.defaultTerrain
}

func (b *Board) terrainOf(unit *unit) terrain {
	if unit == nil {
		return b.defaultTerrain
	}
	return b.terrainAt(unit.Footprint.Anchor)
}

var phaseOrder = [...]faction{factionAlly, factionThirdParty, factionEnemy}

func (b *Board) phaseIndex() int {
	for index, faction := range phaseOrder {
		if faction == b.phase {
			return b.turn*len(phaseOrder) + index
		}
	}
	return b.turn * len(phaseOrder)
}

func (b *Board) unit(id string) *unit {
	for index := range b.units {
		if b.units[index].ID == id {
			return &b.units[index]
		}
	}
	return nil
}

// The command 'act' reads this gate; the reporting commands do not, because
// a report of a unit that acted is still the answer to the question.
func (b *Board) activatable(unitID string) (*unit, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return nil, err
	}
	if unit.Faction != b.phase {
		return nil, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			battle.ErrOffPhase, unitID, unit.Faction, b.phase)
	}
	if unit.Acted {
		return nil, fmt.Errorf("%w: %q", battle.ErrActed, unitID)
	}
	return unit, nil
}

func (b *Board) livingUnit(id string) (*unit, error) {
	unit := b.unit(id)
	if unit == nil {
		return nil, fmt.Errorf("%w: %q", battle.ErrNoUnit, id)
	}
	if !unit.alive() {
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

func (b *Board) reachableCells(unitID string) ([]cell, error) {
	unit := b.unit(unitID)
	if unit == nil {
		return nil, fmt.Errorf("the board holds no unit %q", unitID)
	}
	return sortedCells(b.reachableAnchors(unit)), nil
}

func (b *Board) reachableAnchors(unit *unit) cellSet {
	return reachableAnchors(unit.Footprint, unit.Mech.MoveRange,
		b.blockingCells(unit), b.occupiedCells(unit), b.bounds)
}

func (b *Board) byFaction(faction faction) []*unit {
	var out []*unit
	for index := range b.units {
		other := &b.units[index]
		if other.Faction == faction && other.alive() {
			out = append(out, other)
		}
	}
	return out
}

func (b *Board) targetsOf(unit *unit) []*unit {
	return b.byFaction(unit.Faction.opposing())
}

func (b *Board) blockingCells(unit *unit) cellSet {
	out := cellSet{}
	for index := range b.units {
		other := &b.units[index]
		if other.ID == unit.ID || !other.alive() || other.Faction == unit.Faction {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}

func (b *Board) occupiedCells(unit *unit) cellSet {
	out := cellSet{}
	for index := range b.units {
		other := &b.units[index]
		if other.ID == unit.ID || !other.alive() {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}
