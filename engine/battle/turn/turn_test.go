package turn

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func turnBoard(phase battle.Faction, turn int, units ...battle.Unit) *state.Battle {
	bounds := battle.Bounds{{0, 0}, {5, 4}}
	out := state.FromContract(battle.BattleState{Bounds: &bounds, Units: units,
		Phase: phase, Turn: turn})
	return &out
}

func basicUnit(faction battle.Faction, x, y int) battle.Unit {
	return battle.Unit{
		Faction: faction,
		Pos:     battle.Cell{x, y}, Size: battle.Cell{1, 1},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140,
		Mech: battle.Mech{MoveRange: 1}, Pilot: battle.Pilot{},
	}
}

func TestPendingHoldsTheLivingUnitsOfTheSideThatDidNotAct(t *testing.T) {
	acted := basicUnit(battle.FactionAlly, 1, 2)
	acted.Acted = true
	dead := basicUnit(battle.FactionAlly, 1, 3)
	dead.HP = 0
	board := turnBoard(battle.FactionAlly, 1, basicUnit(battle.FactionAlly, 1, 1), acted, dead, basicUnit(battle.FactionEnemy, 4, 4))

	if ids := Pending(board, battle.FactionAlly); !reflect.DeepEqual(ids, []int{0}) {
		t.Fatalf("pending: %v", ids)
	}
}

func TestGoneNamesTheSidesWithNoLivingUnit(t *testing.T) {
	dead := basicUnit(battle.FactionEnemy, 4, 4)
	dead.HP = 0
	board := turnBoard(battle.FactionAlly, 1, basicUnit(battle.FactionAlly, 1, 1), dead)

	if got := Gone(board); !reflect.DeepEqual(got, []battle.Faction{battle.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
	board.Units[0].Value.HP = 0
	if got := Gone(board); !reflect.DeepEqual(got, []battle.Faction{battle.FactionAlly, battle.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := basicUnit(battle.FactionAlly, 1, 1)
	board := turnBoard(battle.FactionAlly, 1, last)
	board.Units[0].Value.HP = 0

	if got := Advance(board); len(got) != 0 || board.Phase != battle.FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}
