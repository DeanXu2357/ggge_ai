// Package board holds the board of one battle: the state, the rules that
// move it, and the codec that carries it over the wire. The package
// 'engine/battle' above it holds the contract that a caller reaches the
// board through.
package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	bounds         battle.Bounds
	units          []battle.Unit
	phase          battle.Faction
	turn           int
	defaultTerrain battle.Terrain
	terrainCells   map[battle.Cell]battle.Terrain
}

func New(bounds battle.Bounds, units []battle.Unit) (*Board, error) {
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

func (b *Board) Roster() []battle.Unit {
	return b.units
}

func (b *Board) TerrainAt(cell battle.Cell) battle.Terrain {
	if kind, declared := b.terrainCells[cell]; declared {
		return kind
	}
	return b.defaultTerrain
}

func (b *Board) TerrainOf(unit *battle.Unit) battle.Terrain {
	if unit == nil {
		return b.defaultTerrain
	}
	return b.TerrainAt(unit.Footprint.Anchor)
}

var PhaseOrder = [...]battle.Faction{battle.FactionAlly, battle.FactionThirdParty, battle.FactionEnemy}

func (b *Board) PhaseIndex() int {
	for index, faction := range PhaseOrder {
		if faction == b.phase {
			return b.turn*len(PhaseOrder) + index
		}
	}
	return b.turn * len(PhaseOrder)
}

func (b *Board) Unit(id string) *battle.Unit {
	for index := range b.units {
		if b.units[index].ID == id {
			return &b.units[index]
		}
	}
	return nil
}

// The command 'act' reads this gate; the reporting commands do not, because
// a report of a unit that acted is still the answer to the question.
func (b *Board) Activatable(unitID string) (*battle.Unit, error) {
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

func (b *Board) livingUnit(id string) (*battle.Unit, error) {
	unit := b.Unit(id)
	if unit == nil {
		return nil, fmt.Errorf("%w: %q", battle.ErrNoUnit, id)
	}
	if !unit.Alive() {
		return nil, fmt.Errorf("%w: %q", battle.ErrDestroyed, id)
	}
	return unit, nil
}

func (b *Board) ReachableCells(unitID string) ([]battle.Cell, error) {
	unit := b.Unit(unitID)
	if unit == nil {
		return nil, fmt.Errorf("the board holds no unit %q", unitID)
	}
	return SortedCells(b.reachableAnchors(unit)), nil
}

func (b *Board) reachableAnchors(unit *battle.Unit) CellSet {
	return ReachableAnchors(unit.Footprint, unit.Mech.MoveRange,
		b.BlockingCells(unit), b.OccupiedCells(unit), b.bounds)
}

func (b *Board) ByFaction(faction battle.Faction) []*battle.Unit {
	var out []*battle.Unit
	for index := range b.units {
		other := &b.units[index]
		if other.Faction == faction && other.Alive() {
			out = append(out, other)
		}
	}
	return out
}

func (b *Board) TargetsOf(unit *battle.Unit) []*battle.Unit {
	return b.ByFaction(unit.Faction.Opposing())
}

func (b *Board) BlockingCells(unit *battle.Unit) CellSet {
	out := CellSet{}
	for index := range b.units {
		other := &b.units[index]
		if other.ID == unit.ID || !other.Alive() || other.Faction == unit.Faction {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}

func (b *Board) OccupiedCells(unit *battle.Unit) CellSet {
	out := CellSet{}
	for index := range b.units {
		other := &b.units[index]
		if other.ID == unit.ID || !other.Alive() {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}
