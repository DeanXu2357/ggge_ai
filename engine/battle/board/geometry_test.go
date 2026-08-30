package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var oneCell = state.Size{1, 1}

func unitAt(id string, faction state.Faction, anchor state.Cell) state.Unit {
	return state.Unit{ID: id, Faction: faction,
		Footprint: state.Footprint{Anchor: anchor, Size: oneCell}, HP: 100,
		Mech: &def.Mech{}, Pilot: &def.Pilot{}}
}

func board(units ...state.Unit) *Board {
	return &Board{state: state.Board{
		Bounds: state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{4, 4}}, Units: units,
		Phase: state.FactionAlly, Turn: 1}}
}

func ids(units []*state.Unit) []string {
	out := make([]string, 0, len(units))
	for _, one := range units {
		out = append(out, one.ID)
	}
	return out
}

func reach(t *testing.T, b *Board, id string) []state.Cell {
	t.Helper()
	unit := b.unit(id)
	if unit == nil {
		t.Fatalf("the board holds no unit %q", id)
	}
	return b.reachableCells(unit)
}

func set(cells []state.Cell) geometry.CellSet {
	out := geometry.CellSet{}
	for _, cell := range cells {
		out[cell] = true
	}
	return out
}

func TestReachIsTheDiamondOfTheMoveRange(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{2, 2}))
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
	if near[state.Cell{3, 3}] {
		t.Fatal("a diagonal cell costs two steps, and this unit holds one")
	}
}

func TestReachDropsTheCellsBehindABlocker(t *testing.T) {
	b := board(
		unitAt("a1", state.FactionAlly, state.Cell{2, 2}),
		unitAt("e1", state.FactionEnemy, state.Cell{2, 3}),
	)
	b.state.Units[0].Mech.MoveRange = 2

	cells := reach(t, b, "a1")

	want := []state.Cell{
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
		unitAt("a1", state.FactionAlly, state.Cell{2, 2}),
		unitAt("a2", state.FactionAlly, state.Cell{2, 3}),
	)
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if cells[state.Cell{2, 3}] {
		t.Fatal("the cell of the ally holds a unit and is no destination")
	}
	if !cells[state.Cell{2, 4}] {
		t.Fatal("the path through the ally is open")
	}
	if len(cells) != 12 {
		t.Fatalf("cells: %d", len(cells))
	}
}

func TestAThirdPartyBlocksThePathOfAnAlly(t *testing.T) {
	b := board(
		unitAt("a1", state.FactionAlly, state.Cell{2, 2}),
		unitAt("t1", state.FactionThirdParty, state.Cell{2, 3}),
	)
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if cells[state.Cell{2, 4}] {
		t.Fatal("a unit of another faction blocks the path")
	}
}

func TestReachStopsAtTheBoardBounds(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{0, 0}))
	b.state.Units[0].Mech.MoveRange = 1

	cells := reach(t, b, "a1")

	want := []state.Cell{{0, 0}, {0, 1}, {1, 0}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("cells: %v", cells)
	}
}

func TestTargetsOfAnswersTheOpposingFaction(t *testing.T) {
	b := board(
		unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("e1", state.FactionEnemy, state.Cell{1, 0}),
		unitAt("t1", state.FactionThirdParty, state.Cell{2, 0}),
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
		unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("e1", state.FactionEnemy, state.Cell{2, 1}),
	)
	b.state.Units[0].Footprint.Size = state.Size{2, 2}
	b.state.Units[0].Mech.MoveRange = 1

	cells := reach(t, b, "a1")

	want := []state.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("the anchor (1,0) is free and the footprint of that anchor holds the foe: %v", cells)
	}
}

func TestReachStopsWhereTheFootprintLeavesTheBoard(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{2, 2}))
	b.state.Units[0].Footprint.Size = state.Size{2, 2}
	b.state.Units[0].Mech.MoveRange = 2

	cells := set(reach(t, b, "a1"))

	if cells[state.Cell{4, 2}] || cells[state.Cell{2, 4}] {
		t.Fatal("an anchor on the last row or column puts half of the footprint outside the board")
	}
	if !cells[state.Cell{3, 3}] {
		t.Fatal("the last anchor that holds the whole footprint is on the board")
	}
	if len(cells) != 11 {
		t.Fatalf("cells: %d, against the 13 of the diamond less the 2 that the footprint loses", len(cells))
	}
}

func TestAnAllyLetsTheFootprintThroughAndDeniesEveryCellItCovers(t *testing.T) {
	b := board(
		unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("a2", state.FactionAlly, state.Cell{2, 1}),
	)
	b.state.Units[0].Footprint.Size = state.Size{2, 2}
	b.state.Units[0].Mech.MoveRange = 2

	cells := reach(t, b, "a1")

	want := []state.Cell{{0, 0}, {0, 1}, {0, 2}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("an anchor whose footprint covers the ally is no destination: %v", cells)
	}
}

func TestTheReachOfAUnitThatIsNotOnTheBoardIsAnError(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{2, 2}))

	cells, err := b.ReachableCells("ghost")

	if !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("cells: %v, error: %v", cells, err)
	}
}

func TestAUnitThatCannotMoveKeepsItsOwnCell(t *testing.T) {
	b := board(
		unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("e1", state.FactionEnemy, state.Cell{1, 0}),
		unitAt("e2", state.FactionEnemy, state.Cell{0, 1}),
	)
	b.state.Units[0].Mech.MoveRange = 3

	cells := reach(t, b, "a1")

	if !reflect.DeepEqual(cells, []state.Cell{{0, 0}}) {
		t.Fatalf("a unit that is boxed in answers its own cell, not nothing: %v", cells)
	}
}
