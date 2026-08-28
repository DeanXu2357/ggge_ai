package board

import (
	"sort"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var steps = [4]battle.Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}}

func SpanDistance(a, b battle.Footprint) int {
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

func FootprintClear(footprint battle.Footprint, taken battle.CellSet) bool {
	for _, cell := range footprint.Cells() {
		if taken[cell] {
			return false
		}
	}
	return true
}

func addFootprint(set battle.CellSet, footprint battle.Footprint) {
	for _, cell := range footprint.Cells() {
		set[cell] = true
	}
}

func ReachableAnchors(from battle.Footprint, budget int, blocked, occupied battle.CellSet, bounds battle.Bounds) battle.CellSet {
	seen := battle.CellSet{from.Anchor: true}
	out := battle.CellSet{from.Anchor: true}
	frontier := []walk{{from.Anchor, 0}}
	for len(frontier) > 0 {
		step := frontier[0]
		frontier = frontier[1:]
		if step.spent == budget {
			continue
		}
		for _, delta := range steps {
			next := battle.Footprint{Anchor: battle.Cell{step.cell[0] + delta[0], step.cell[1] + delta[1]}, Size: from.Size}
			if seen[next.Anchor] || !next.Within(bounds) || !FootprintClear(next, blocked) {
				continue
			}
			seen[next.Anchor] = true
			frontier = append(frontier, walk{next.Anchor, step.spent + 1})
			if FootprintClear(next, occupied) {
				out[next.Anchor] = true
			}
		}
	}
	return out
}

type walk struct {
	cell  battle.Cell
	spent int
}

func NearestFreeCell(footprint battle.Footprint, taken battle.CellSet) battle.Cell {
	seen := battle.CellSet{footprint.Anchor: true}
	frontier := []battle.Cell{footprint.Anchor}
	for len(frontier) > 0 {
		anchor := frontier[0]
		frontier = frontier[1:]
		if FootprintClear(battle.Footprint{Anchor: anchor, Size: footprint.Size}, taken) {
			return anchor
		}
		for _, delta := range steps {
			next := battle.Cell{anchor[0] + delta[0], anchor[1] + delta[1]}
			if !seen[next] {
				seen[next] = true
				frontier = append(frontier, next)
			}
		}
	}
	return footprint.Anchor
}

func SortedCells(set battle.CellSet) []battle.Cell {
	out := cellSlice(set)
	sort.Slice(out, func(i, j int) bool { return out[i].Before(out[j]) })
	return out
}

func footprintAt(unit *battle.Unit, anchor battle.Cell) battle.Footprint {
	return battle.Footprint{Anchor: anchor, Size: unit.Footprint.Size}
}

func cellFootprint(cell battle.Cell) battle.Footprint {
	return battle.Footprint{Anchor: cell, Size: battle.Size{1, 1}}
}

func cellSlice(set battle.CellSet) []battle.Cell {
	out := make([]battle.Cell, 0, len(set))
	for cell := range set {
		out = append(out, cell)
	}
	return out
}
