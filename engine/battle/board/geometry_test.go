package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var oneCell = battle.Cell{1, 1}

func unitAt(faction battle.Faction, anchor battle.Cell) battle.Unit {
	return battle.Unit{Faction: faction,
		Pos: anchor, Size: oneCell, HP: 100,
		Mech: battle.Mech{}, Pilot: battle.Pilot{}}
}

func board(units ...battle.Unit) *Board {
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	return &Board{state: state.FromContract(battle.BattleState{
		Bounds: &bounds, Units: units,
		Phase: battle.FactionAlly, Turn: 1})}
}

func TestTargetsOfAnswersTheOpposingFaction(t *testing.T) {
	b := board(
		unitAt(battle.FactionAlly, battle.Cell{0, 0}),
		unitAt(battle.FactionEnemy, battle.Cell{1, 0}),
		unitAt(battle.FactionThirdParty, battle.Cell{2, 0}),
	)

	if got := targetsOf(b, 0); !reflect.DeepEqual(got, []int{1}) {
		t.Fatalf("targets of the ally: %v", got)
	}
	if got := targetsOf(b, 1); !reflect.DeepEqual(got, []int{0}) {
		t.Fatalf("targets of the enemy: %v", got)
	}
	if got := targetsOf(b, 2); !reflect.DeepEqual(got, []int{0}) {
		t.Fatalf("targets of the third party: %v", got)
	}
}

func TestTheReachOfAUnitThatIsNotOnTheBoardIsAnError(t *testing.T) {
	b := board(unitAt(battle.FactionAlly, battle.Cell{2, 2}))

	cells, err := b.ReachableCells(9)

	if !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("cells: %v, error: %v", cells, err)
	}
}
