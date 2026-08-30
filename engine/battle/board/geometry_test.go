package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
)

var oneCell = battle.Cell{1, 1}

func unitAt(id string, faction battle.Faction, anchor battle.Cell) battle.Unit {
	return battle.Unit{ID: id, Faction: faction,
		Pos: anchor, Size: oneCell, HP: 100,
		Mech: battle.Mech{}, Pilot: battle.Pilot{}}
}

func board(units ...battle.Unit) *Board {
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	return &Board{state: battle.BattleState{
		Bounds: &bounds, Units: units,
		Phase: battle.FactionAlly, Turn: 1}}
}

func ids(units []*battle.Unit) []string {
	out := make([]string, 0, len(units))
	for _, one := range units {
		out = append(out, one.ID)
	}
	return out
}

func reach(t *testing.T, b *Board, id string) []battle.Cell {
	t.Helper()
	unit := b.state.Unit(id)
	if unit == nil {
		t.Fatalf("the board holds no unit %q", id)
	}
	return geometry.SortedCells(geometry.ReachableAnchors(&b.state, unit))
}

func set(cells []battle.Cell) geometry.CellSet {
	out := geometry.CellSet{}
	for _, cell := range cells {
		out[cell] = true
	}
	return out
}

func TestReachIsTheDiamondOfTheMoveRange(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}))
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if len(cells) != 13 {
		t.Fatalf("cells: %d, against the 13 of the diamond", len(cells))
	}

	b.state.Units[0].Mech.MoveRange = 1
	near := set(reach(t, b, "a1"))

	if len(near) != 5 {
		t.Fatalf("cells: %d, against the 5 of the diamond", len(near))
	}
	if near[battle.Cell{3, 3}] {
		t.Fatal("a diagonal cell costs two steps, and this unit holds one")
	}
}

func TestReachDropsTheCellsBehindABlocker(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{2, 3}),
	)
	b.state.Units[0].Mech.MoveRange = 2

	cells := reach(t, b, "a1")

	want := []battle.Cell{
		{0, 2},
		{1, 1}, {1, 2}, {1, 3},
		{2, 0}, {2, 1}, {2, 2},
		{3, 1}, {3, 2}, {3, 3},
		{4, 2},
	}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("cells: %v", cells)
	}
}

func TestAnAllyLetsThePathThroughAndKeepsItsCell(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}),
		unitAt("a2", battle.FactionAlly, battle.Cell{2, 3}),
	)
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if cells[battle.Cell{2, 3}] {
		t.Fatal("the cell of the ally holds a unit and is no destination")
	}
	if !cells[battle.Cell{2, 4}] {
		t.Fatal("the path through the ally is open")
	}
	if len(cells) != 12 {
		t.Fatalf("cells: %d", len(cells))
	}
}

func TestAThirdPartyBlocksThePathOfAnAlly(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}),
		unitAt("t1", battle.FactionThirdParty, battle.Cell{2, 3}),
	)
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if cells[battle.Cell{2, 4}] {
		t.Fatal("a unit of another faction blocks the path")
	}
}

func TestReachStopsAtTheBoardBounds(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}))
	b.state.Units[0].Mech.MoveRange = 1

	cells := reach(t, b, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}, {1, 0}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("cells: %v", cells)
	}
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

func TestReachOfAFootprintNeedsEveryCellOfIt(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{2, 1}),
	)
	b.state.Units[0].Size = battle.Cell{2, 2}
	b.state.Units[0].Mech.MoveRange = 1

	cells := reach(t, b, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("the anchor (1,0) is free and the footprint of that anchor holds the foe: %v", cells)
	}
}

func TestReachStopsWhereTheFootprintLeavesTheBoard(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}))
	b.state.Units[0].Size = battle.Cell{2, 2}
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if cells[battle.Cell{4, 2}] || cells[battle.Cell{2, 4}] {
		t.Fatal("an anchor on the last row or column puts half of the footprint outside the board")
	}
	if !cells[battle.Cell{3, 3}] {
		t.Fatal("the last anchor that holds the whole footprint is on the board")
	}
	if len(cells) != 11 {
		t.Fatalf("cells: %d, against the 13 of the diamond less the 2 that the footprint loses", len(cells))
	}
}

func TestAnAllyLetsTheFootprintThroughAndDeniesEveryCellItCovers(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("a2", battle.FactionAlly, battle.Cell{2, 1}),
	)
	b.state.Units[0].Size = battle.Cell{2, 2}
	b.state.Units[0].Mech.MoveRange = 2

	cells := reach(t, b, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}, {0, 2}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("an anchor whose footprint covers the ally is no destination: %v", cells)
	}
}

func TestTheReachOfAUnitThatIsNotOnTheBoardIsAnError(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{2, 2}))

	cells, err := b.ReachableCells("ghost")

	if !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("cells: %v, error: %v", cells, err)
	}
}

func TestAUnitThatCannotMoveKeepsItsOwnCell(t *testing.T) {
	b := board(
		unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{1, 0}),
		unitAt("e2", battle.FactionEnemy, battle.Cell{0, 1}),
	)
	b.state.Units[0].Mech.MoveRange = 3

	cells := reach(t, b, "a1")

	if !reflect.DeepEqual(cells, []battle.Cell{{0, 0}}) {
		t.Fatalf("a unit that is boxed in answers its own cell, not nothing: %v", cells)
	}
}
