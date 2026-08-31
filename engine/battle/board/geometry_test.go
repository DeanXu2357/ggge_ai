package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var oneCell = battle.Cell{1, 1}

func unitAt(id string, faction battle.Faction, anchor battle.Cell) battle.Unit {
	return battle.Unit{ID: id, Faction: faction,
		Pos: anchor, Size: oneCell, HP: 100,
		Mech: battle.Mech{}, Pilot: battle.Pilot{}}
}

func board(units ...battle.Unit) *Board {
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	return &Board{state: state.FromContract(battle.BattleState{
		Bounds: &bounds, Units: units,
		Phase: battle.FactionAlly, Turn: 1})}
}

func ids(units []*state.Unit) []string {
	out := make([]string, 0, len(units))
	for _, one := range units {
		out = append(out, one.ID)
	}
	return out
}

func TestTargetsOfAnswersTheOpposingFaction(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{1, 0}),
		unitAt("t1", battle.FactionThirdParty, battle.Cell{2, 0}),
	)

	if got := ids(targetsOf(b, &b.state.Units[0])); !reflect.DeepEqual(got, []string{"e1"}) {
		t.Fatalf("targets of the ally: %v", got)
	}
	if got := ids(targetsOf(b, &b.state.Units[1])); !reflect.DeepEqual(got, []string{"a1"}) {
		t.Fatalf("targets of the enemy: %v", got)
	}
	if got := ids(targetsOf(b, &b.state.Units[2])); !reflect.DeepEqual(got, []string{"a1"}) {
		t.Fatalf("targets of the third party: %v", got)
	}
}

func TestTheReachOfAUnitThatIsNotOnTheBoardIsAnError(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}))

	cells, err := b.ReachableCells("ghost")

	if !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("cells: %v, error: %v", cells, err)
	}
}
