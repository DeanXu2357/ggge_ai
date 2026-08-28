package board

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var oneCell = battle.Size{1, 1}

func unit(id string, faction battle.Faction, anchor battle.Cell) battle.Unit {
	return battle.Unit{ID: id, Faction: faction, Footprint: battle.Footprint{Anchor: anchor, Size: oneCell}, HP: 100}
}

func board(units ...battle.Unit) *Board {
	return &Board{bounds: battle.Bounds{Low: battle.Cell{0, 0}, High: battle.Cell{4, 4}}, units: units,
		phase: battle.FactionAlly, turn: 1}
}

func ids(units []*battle.Unit) []string {
	out := make([]string, 0, len(units))
	for _, one := range units {
		out = append(out, one.ID)
	}
	return out
}

func reach(t *testing.T, state *Board, id string) []battle.Cell {
	t.Helper()
	cells, err := state.ReachableCells(id)
	if err != nil {
		t.Fatalf("reach: %v", err)
	}
	return cells
}

func set(cells []battle.Cell) CellSet {
	out := CellSet{}
	for _, cell := range cells {
		out[cell] = true
	}
	return out
}

func at(cell battle.Cell) battle.Footprint {
	return battle.Footprint{Anchor: cell, Size: oneCell}
}

func TestADiagonalNeighbourIsTwoStepsAway(t *testing.T) {
	if got := SpanDistance(at(battle.Cell{2, 2}), at(battle.Cell{3, 3})); got != 2 {
		t.Fatalf("diagonal distance: %d", got)
	}
	if got := SpanDistance(at(battle.Cell{2, 2}), at(battle.Cell{2, 3})); got != 1 {
		t.Fatalf("orthogonal distance: %d", got)
	}
	if got := SpanDistance(at(battle.Cell{4, 1}), at(battle.Cell{1, 3})); got != 5 {
		t.Fatalf("distance: %d", got)
	}
}

func TestReachIsTheDiamondOfTheMoveRange(t *testing.T) {
	state := board(unit("a1", battle.FactionAlly, battle.Cell{2, 2}))
	state.units[0].Mech.MoveRange = 2

	cells := set(reach(t, state, "a1"))

	if len(cells) != 13 {
		t.Fatalf("cells: %d, against the 13 of the diamond", len(cells))
	}

	state.units[0].Mech.MoveRange = 1
	near := set(reach(t, state, "a1"))

	if len(near) != 5 {
		t.Fatalf("cells: %d, against the 5 of the diamond", len(near))
	}
	if near[battle.Cell{3, 3}] {
		t.Fatal("a diagonal cell costs two steps, and this unit holds one")
	}
}

func TestReachDropsTheCellsBehindABlocker(t *testing.T) {
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{2, 2}),
		unit("e1", battle.FactionEnemy, battle.Cell{2, 3}),
	)
	state.units[0].Mech.MoveRange = 2

	cells := reach(t, state, "a1")

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
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{2, 2}),
		unit("a2", battle.FactionAlly, battle.Cell{2, 3}),
	)
	state.units[0].Mech.MoveRange = 2

	cells := set(reach(t, state, "a1"))

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
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{2, 2}),
		unit("t1", battle.FactionThirdParty, battle.Cell{2, 3}),
	)
	state.units[0].Mech.MoveRange = 2

	cells := set(reach(t, state, "a1"))

	if cells[battle.Cell{2, 4}] {
		t.Fatal("a unit of another faction blocks the path")
	}
}

func TestReachStopsAtTheBoardBounds(t *testing.T) {
	state := board(unit("a1", battle.FactionAlly, battle.Cell{0, 0}))
	state.units[0].Mech.MoveRange = 1

	cells := reach(t, state, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}, {1, 0}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("cells: %v", cells)
	}
}

func TestNearestFreeCellSearchesOnTheOrthogonalSteps(t *testing.T) {
	taken := CellSet{{0, 0}: true}
	one := battle.Footprint{Anchor: battle.Cell{0, 0}, Size: oneCell}

	if got := NearestFreeCell(one, taken); got != (battle.Cell{-1, 0}) {
		t.Fatalf("first free cell: %v", got)
	}

	for _, cell := range []battle.Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}} {
		taken[cell] = true
	}

	if got := NearestFreeCell(one, taken); got != (battle.Cell{-2, 0}) {
		t.Fatalf("the search leaves the ring on a step of the board, not on a diagonal: %v", got)
	}
}

func TestNearestFreeCellFitsTheWholeFootprint(t *testing.T) {
	taken := CellSet{{1, 1}: true}

	wide := battle.Footprint{Anchor: battle.Cell{0, 0}, Size: battle.Size{2, 2}}
	if got := NearestFreeCell(wide, taken); got != (battle.Cell{-1, 0}) {
		t.Fatalf("the anchor is free and the footprint is not: %v", got)
	}

	one := battle.Footprint{Anchor: battle.Cell{0, 0}, Size: oneCell}
	if got := NearestFreeCell(one, taken); got != (battle.Cell{0, 0}) {
		t.Fatalf("a footprint of one cell keeps the anchor: %v", got)
	}
}

func TestTargetsOfAnswersTheOpposingFaction(t *testing.T) {
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unit("e1", battle.FactionEnemy, battle.Cell{1, 0}),
		unit("t1", battle.FactionThirdParty, battle.Cell{2, 0}),
	)

	if got := ids(state.TargetsOf(&state.units[0])); !reflect.DeepEqual(got, []string{"e1"}) {
		t.Fatalf("targets of the ally: %v", got)
	}
	if got := ids(state.TargetsOf(&state.units[1])); !reflect.DeepEqual(got, []string{"a1"}) {
		t.Fatalf("targets of the enemy: %v", got)
	}
	if got := ids(state.TargetsOf(&state.units[2])); !reflect.DeepEqual(got, []string{"a1"}) {
		t.Fatalf("targets of the third party: %v", got)
	}
}

func TestTheDistanceOfTwoFootprintsIsTheLeastDistanceOfTheirCells(t *testing.T) {
	big := battle.Footprint{Anchor: battle.Cell{0, 0}, Size: battle.Size{2, 2}}
	tall := battle.Footprint{Anchor: battle.Cell{0, 0}, Size: battle.Size{2, 3}}

	if got := SpanDistance(big, battle.Footprint{Anchor: battle.Cell{2, 0}, Size: oneCell}); got != 1 {
		t.Fatalf("a foe beside the footprint is one step away, not two: %d", got)
	}
	if got := SpanDistance(big, battle.Footprint{Anchor: battle.Cell{2, 1}, Size: oneCell}); got != 1 {
		t.Fatalf("the near cell of the footprint decides, not the anchor: %d", got)
	}
	if got := SpanDistance(tall, battle.Footprint{Anchor: battle.Cell{4, 1}, Size: battle.Size{2, 2}}); got != 3 {
		t.Fatalf("two footprints measure from their near cells: %d", got)
	}
	if got := SpanDistance(at(battle.Cell{2, 2}), at(battle.Cell{3, 3})); got != 2 {
		t.Fatalf("two footprints of one cell keep the cell distance: %d", got)
	}
	if got := SpanDistance(big, battle.Footprint{Anchor: battle.Cell{1, 1}, Size: battle.Size{2, 2}}); got != 0 {
		t.Fatalf("two footprints that share a cell are at distance zero: %d", got)
	}
}

func TestReachOfAFootprintNeedsEveryCellOfIt(t *testing.T) {
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unit("e1", battle.FactionEnemy, battle.Cell{2, 1}),
	)
	state.units[0].Footprint.Size = battle.Size{2, 2}
	state.units[0].Mech.MoveRange = 1

	cells := reach(t, state, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("the anchor (1,0) is free and the footprint of that anchor holds the foe: %v", cells)
	}
}

func TestReachStopsWhereTheFootprintLeavesTheBoard(t *testing.T) {
	state := board(unit("a1", battle.FactionAlly, battle.Cell{2, 2}))
	state.units[0].Footprint.Size = battle.Size{2, 2}
	state.units[0].Mech.MoveRange = 2

	cells := set(reach(t, state, "a1"))

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
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unit("a2", battle.FactionAlly, battle.Cell{2, 1}),
	)
	state.units[0].Footprint.Size = battle.Size{2, 2}
	state.units[0].Mech.MoveRange = 2

	cells := reach(t, state, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}, {0, 2}}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("an anchor whose footprint covers the ally is no destination: %v", cells)
	}
}

func TestTheReachOfAUnitThatIsNotOnTheBoardIsAnError(t *testing.T) {
	state := board(unit("a1", battle.FactionAlly, battle.Cell{2, 2}))

	cells, err := state.ReachableCells("ghost")

	if err == nil {
		t.Fatalf("cells: %v", cells)
	}
}

func TestAUnitThatCannotMoveKeepsItsOwnCell(t *testing.T) {
	state := board(
		unit("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unit("e1", battle.FactionEnemy, battle.Cell{1, 0}),
		unit("e2", battle.FactionEnemy, battle.Cell{0, 1}),
	)
	state.units[0].Mech.MoveRange = 3

	cells := reach(t, state, "a1")

	if !reflect.DeepEqual(cells, []battle.Cell{{0, 0}}) {
		t.Fatalf("a unit that is boxed in answers its own cell, not nothing: %v", cells)
	}
}
