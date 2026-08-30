package turn

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func turnBoard(phase state.Faction, turn int, units ...state.Unit) *state.Board {
	return &state.Board{Bounds: state.Bounds{High: state.Cell{5, 4}}, Units: units,
		Phase: phase, Turn: turn}
}

func basicUnit(id string, faction state.Faction, x, y int) state.Unit {
	return state.Unit{
		ID: id, Faction: faction,
		Footprint: state.Footprint{Anchor: state.Cell{x, y}, Size: state.Size{1, 1}},
		HP:        100, MaxHP: 100, EN: 100, ENMax: 140,
		Mech: &def.Mech{MoveRange: 1}, Pilot: &def.Pilot{},
	}
}

func TestPendingHoldsTheLivingUnitsOfTheSideThatDidNotAct(t *testing.T) {
	acted := basicUnit("a2", state.FactionAlly, 1, 2)
	acted.Acted = true
	dead := basicUnit("a3", state.FactionAlly, 1, 3)
	dead.HP = 0
	board := turnBoard(state.FactionAlly, 1, basicUnit("a1", state.FactionAlly, 1, 1), acted, dead, basicUnit("e1", state.FactionEnemy, 4, 4))

	var ids []string
	for _, pending := range Pending(board, state.FactionAlly) {
		ids = append(ids, pending.ID)
	}
	if !reflect.DeepEqual(ids, []string{"a1"}) {
		t.Fatalf("pending: %v", ids)
	}
}

func TestGoneNamesTheSidesWithNoLivingUnit(t *testing.T) {
	dead := basicUnit("e1", state.FactionEnemy, 4, 4)
	dead.HP = 0
	board := turnBoard(state.FactionAlly, 1, basicUnit("a1", state.FactionAlly, 1, 1), dead)

	if got := Gone(board); !reflect.DeepEqual(got, []state.Faction{state.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
	board.Unit("a1").HP = 0
	if got := Gone(board); !reflect.DeepEqual(got, []state.Faction{state.FactionAlly, state.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := basicUnit("a1", state.FactionAlly, 1, 1)
	board := turnBoard(state.FactionAlly, 1, last)
	board.Unit("a1").HP = 0

	if got := Advance(board); len(got) != 0 || board.Phase != state.FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}
