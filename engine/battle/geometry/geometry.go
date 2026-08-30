package geometry

import (
	"sort"

	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type CellSet map[state.Cell]bool

var steps = [4]state.Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}}

func Distance(a, b state.Footprint) int {
	return axisGap(a.Anchor[0], a.Size[0], b.Anchor[0], b.Size[0]) +
		axisGap(a.Anchor[1], a.Size[1], b.Anchor[1], b.Size[1])
}

func axisGap(lowA, spanA, lowB, spanB int) int {
	if gap := lowB - (lowA + spanA - 1); gap > 0 {
		return gap
	}
	if gap := lowA - (lowB + spanB - 1); gap > 0 {
		return gap
	}
	return 0
}

func footprintClear(footprint state.Footprint, taken CellSet) bool {
	for _, cell := range footprint.Cells() {
		if taken[cell] {
			return false
		}
	}
	return true
}

func AddFootprint(set CellSet, footprint state.Footprint) {
	for _, cell := range footprint.Cells() {
		set[cell] = true
	}
}

func ReachableAnchors(board *state.Board, unit *state.Unit) CellSet {
	return reachableAnchors(unit.Footprint, unit.Mech.MoveRange,
		Blocking(board, unit), Occupied(board, unit.ID), board.Bounds)
}

func reachableAnchors(from state.Footprint, budget int, blocked, occupied CellSet, bounds state.Bounds) CellSet {
	seen := CellSet{from.Anchor: true}
	out := CellSet{from.Anchor: true}
	frontier := []walk{{from.Anchor, 0}}
	for len(frontier) > 0 {
		step := frontier[0]
		frontier = frontier[1:]
		if step.spent == budget {
			continue
		}
		for _, delta := range steps {
			next := state.Footprint{Anchor: state.Cell{step.cell[0] + delta[0], step.cell[1] + delta[1]}, Size: from.Size}
			if seen[next.Anchor] || !next.Within(bounds) || !footprintClear(next, blocked) {
				continue
			}
			seen[next.Anchor] = true
			frontier = append(frontier, walk{next.Anchor, step.spent + 1})
			if footprintClear(next, occupied) {
				out[next.Anchor] = true
			}
		}
	}
	return out
}

type walk struct {
	cell  state.Cell
	spent int
}

func Blocking(board *state.Board, unit *state.Unit) CellSet {
	out := CellSet{}
	for index := range board.Units {
		other := &board.Units[index]
		if other.ID == unit.ID || other.HP <= 0 || other.Faction == unit.Faction {
			continue
		}
		AddFootprint(out, other.Footprint)
	}
	return out
}

func Occupied(board *state.Board, except string) CellSet {
	out := CellSet{}
	for index := range board.Units {
		other := &board.Units[index]
		if other.ID == except || other.HP <= 0 {
			continue
		}
		AddFootprint(out, other.Footprint)
	}
	return out
}

func nearestFreeCell(from state.Footprint, taken CellSet) state.Cell {
	seen := CellSet{from.Anchor: true}
	frontier := []state.Cell{from.Anchor}
	for len(frontier) > 0 {
		anchor := frontier[0]
		frontier = frontier[1:]
		if footprintClear(state.Footprint{Anchor: anchor, Size: from.Size}, taken) {
			return anchor
		}
		for _, delta := range steps {
			next := state.Cell{anchor[0] + delta[0], anchor[1] + delta[1]}
			if !seen[next] {
				seen[next] = true
				frontier = append(frontier, next)
			}
		}
	}
	return from.Anchor
}

func SortedCells(set CellSet) []state.Cell {
	out := cellSlice(set)
	sort.Slice(out, func(i, j int) bool { return out[i].Before(out[j]) })
	return out
}

func FootprintAt(unit *state.Unit, anchor state.Cell) state.Footprint {
	return state.Footprint{Anchor: anchor, Size: unit.Footprint.Size}
}

func cellSlice(set CellSet) []state.Cell {
	out := make([]state.Cell, 0, len(set))
	for cell := range set {
		out = append(out, cell)
	}
	return out
}
