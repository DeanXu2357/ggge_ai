package board

import (
	"sort"
)

type cellSet map[cell]bool

var steps = [4]cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}}

func spanDistance(a, b footprint) int {
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

func footprintClear(footprint footprint, taken cellSet) bool {
	for _, cell := range footprint.cells() {
		if taken[cell] {
			return false
		}
	}
	return true
}

func addFootprint(set cellSet, footprint footprint) {
	for _, cell := range footprint.cells() {
		set[cell] = true
	}
}

func reachableAnchors(from footprint, budget int, blocked, occupied cellSet, bounds bounds) cellSet {
	seen := cellSet{from.Anchor: true}
	out := cellSet{from.Anchor: true}
	frontier := []walk{{from.Anchor, 0}}
	for len(frontier) > 0 {
		step := frontier[0]
		frontier = frontier[1:]
		if step.spent == budget {
			continue
		}
		for _, delta := range steps {
			next := footprint{Anchor: cell{step.cell[0] + delta[0], step.cell[1] + delta[1]}, Size: from.Size}
			if seen[next.Anchor] || !next.within(bounds) || !footprintClear(next, blocked) {
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
	cell  cell
	spent int
}

func nearestFreeCell(from footprint, taken cellSet) cell {
	seen := cellSet{from.Anchor: true}
	frontier := []cell{from.Anchor}
	for len(frontier) > 0 {
		anchor := frontier[0]
		frontier = frontier[1:]
		if footprintClear(footprint{Anchor: anchor, Size: from.Size}, taken) {
			return anchor
		}
		for _, delta := range steps {
			next := cell{anchor[0] + delta[0], anchor[1] + delta[1]}
			if !seen[next] {
				seen[next] = true
				frontier = append(frontier, next)
			}
		}
	}
	return from.Anchor
}

func sortedCells(set cellSet) []cell {
	out := cellSlice(set)
	sort.Slice(out, func(i, j int) bool { return out[i].before(out[j]) })
	return out
}

func footprintAt(unit *Unit, anchor cell) footprint {
	return footprint{Anchor: anchor, Size: unit.Footprint.Size}
}

func cellFootprint(cell cell) footprint {
	return footprint{Anchor: cell, Size: size{1, 1}}
}

func cellSlice(set cellSet) []cell {
	out := make([]cell, 0, len(set))
	for cell := range set {
		out = append(out, cell)
	}
	return out
}
