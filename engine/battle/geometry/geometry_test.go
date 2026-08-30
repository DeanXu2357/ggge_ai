package geometry

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var oneCell = state.Size{1, 1}

func at(cell state.Cell) state.Footprint {
	return state.Footprint{Anchor: cell, Size: oneCell}
}

func TestADiagonalNeighbourIsTwoStepsAway(t *testing.T) {
	if got := Distance(at(state.Cell{2, 2}), at(state.Cell{3, 3})); got != 2 {
		t.Fatalf("diagonal distance: %d", got)
	}
	if got := Distance(at(state.Cell{2, 2}), at(state.Cell{2, 3})); got != 1 {
		t.Fatalf("orthogonal distance: %d", got)
	}
	if got := Distance(at(state.Cell{4, 1}), at(state.Cell{1, 3})); got != 5 {
		t.Fatalf("distance: %d", got)
	}
}

func TestTheDistanceOfTwoFootprintsIsTheLeastDistanceOfTheirCells(t *testing.T) {
	big := state.Footprint{Anchor: state.Cell{0, 0}, Size: state.Size{2, 2}}
	tall := state.Footprint{Anchor: state.Cell{0, 0}, Size: state.Size{2, 3}}

	if got := Distance(big, state.Footprint{Anchor: state.Cell{2, 0}, Size: oneCell}); got != 1 {
		t.Fatalf("a foe beside the footprint is one step away, not two: %d", got)
	}
	if got := Distance(big, state.Footprint{Anchor: state.Cell{2, 1}, Size: oneCell}); got != 1 {
		t.Fatalf("the near cell of the footprint decides, not the anchor: %d", got)
	}
	if got := Distance(tall, state.Footprint{Anchor: state.Cell{4, 1}, Size: state.Size{2, 2}}); got != 3 {
		t.Fatalf("two footprints measure from their near cells: %d", got)
	}
	if got := Distance(at(state.Cell{2, 2}), at(state.Cell{3, 3})); got != 2 {
		t.Fatalf("two footprints of one cell keep the cell distance: %d", got)
	}
	if got := Distance(big, state.Footprint{Anchor: state.Cell{1, 1}, Size: state.Size{2, 2}}); got != 0 {
		t.Fatalf("two footprints that share a cell are at distance zero: %d", got)
	}
}

func TestNearestFreeCellSearchesOnTheOrthogonalSteps(t *testing.T) {
	taken := CellSet{{0, 0}: true}
	one := state.Footprint{Anchor: state.Cell{0, 0}, Size: oneCell}

	if got := nearestFreeCell(one, taken); got != (state.Cell{-1, 0}) {
		t.Fatalf("first free cell: %v", got)
	}

	for _, cell := range []state.Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}} {
		taken[cell] = true
	}

	if got := nearestFreeCell(one, taken); got != (state.Cell{-2, 0}) {
		t.Fatalf("the search leaves the ring on a step of the board, not on a diagonal: %v", got)
	}
}

func TestNearestFreeCellFitsTheWholeFootprint(t *testing.T) {
	taken := CellSet{{1, 1}: true}

	wide := state.Footprint{Anchor: state.Cell{0, 0}, Size: state.Size{2, 2}}
	if got := nearestFreeCell(wide, taken); got != (state.Cell{-1, 0}) {
		t.Fatalf("the anchor is free and the footprint is not: %v", got)
	}

	one := state.Footprint{Anchor: state.Cell{0, 0}, Size: oneCell}
	if got := nearestFreeCell(one, taken); got != (state.Cell{0, 0}) {
		t.Fatalf("a footprint of one cell keeps the anchor: %v", got)
	}
}
