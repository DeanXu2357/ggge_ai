package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state state.Board
}

type capabilities struct {
	Unit      *state.Unit
	MoveCells []state.Cell
}

type resolution struct {
	Trace     engagement.Trace
	Rotations []turn.Rotation
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

func (b *Board) unit(id string) *state.Unit {
	return b.state.Unit(id)
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
	return geometry.SortedCells(geometry.ReachableAnchors(&b.state, unit)), nil
}

func (b *Board) Act(action *protocol.Decision, dice battle.Dice) ([]any, error) {
	decision, err := DecodeDecision(action)
	if err != nil {
		return nil, err
	}
	resolution, err := b.act(decision, dice)
	if err != nil {
		return nil, err
	}
	return encodeResolution(resolution), nil
}

func (b *Board) act(decision engagement.Decision, dice battle.Dice) (resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return resolution{}, err
	}
	return resolution{Trace: trace, Rotations: b.Advance()}, nil
}

func (b *Board) Advance() []turn.Rotation {
	return turn.Advance(&b.state)
}

// Apply runs one activation and leaves the phase where it stands. The
// differential harness drives it, because the Python oracle rotates the phase
// under a rule of its own.
func (b *Board) Apply(decision engagement.Decision, dice battle.Dice) (engagement.Trace, error) {
	plan, err := engagement.Prepare(&b.state, decision)
	if err != nil {
		return nil, err
	}
	return engagement.Commit(&b.state, plan, dice), nil
}

func (b *Board) ResponseAttacks(action *protocol.Decision, defenderID string) (protocol.ResponseAttacksResponse, error) {
	decision, err := DecodeDecision(action)
	if err != nil {
		return protocol.ResponseAttacksResponse{}, err
	}
	options, err := engagement.Menu(&b.state, decision, defenderID)
	if err != nil {
		return protocol.ResponseAttacksResponse{}, err
	}
	return encodeOptions(options), nil
}
