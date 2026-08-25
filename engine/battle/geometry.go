package battle

import "sort"

var steps = [4]Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}}

type CellSet map[Cell]bool

// Before orders two cells: the column first, the row second.
func (c Cell) Before(other Cell) bool {
	if c[0] != other[0] {
		return c[0] < other[0]
	}
	return c[1] < other[1]
}

func SpanDistance(a, b Footprint) int {
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

func FootprintClear(footprint Footprint, taken CellSet) bool {
	for _, cell := range footprint.Cells() {
		if taken[cell] {
			return false
		}
	}
	return true
}

func addFootprint(set CellSet, footprint Footprint) {
	for _, cell := range footprint.Cells() {
		set[cell] = true
	}
}

func ReachableAnchors(from Footprint, budget int, blocked, occupied CellSet, bounds Bounds) CellSet {
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
			next := Footprint{Anchor: Cell{step.cell[0] + delta[0], step.cell[1] + delta[1]}, Size: from.Size}
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
	cell  Cell
	spent int
}

func NearestFreeCell(footprint Footprint, taken CellSet) Cell {
	seen := CellSet{footprint.Anchor: true}
	frontier := []Cell{footprint.Anchor}
	for len(frontier) > 0 {
		anchor := frontier[0]
		frontier = frontier[1:]
		if FootprintClear(Footprint{Anchor: anchor, Size: footprint.Size}, taken) {
			return anchor
		}
		for _, delta := range steps {
			next := Cell{anchor[0] + delta[0], anchor[1] + delta[1]}
			if !seen[next] {
				seen[next] = true
				frontier = append(frontier, next)
			}
		}
	}
	return footprint.Anchor
}

func SortedCells(set CellSet) []Cell {
	out := cellSlice(set)
	sort.Slice(out, func(i, j int) bool { return out[i].Before(out[j]) })
	return out
}

func footprintAt(unit *Unit, anchor Cell) Footprint {
	return Footprint{Anchor: anchor, Size: unit.Footprint.Size}
}

func cellFootprint(cell Cell) Footprint {
	return Footprint{Anchor: cell, Size: Size{1, 1}}
}

func cellSlice(set CellSet) []Cell {
	out := make([]Cell, 0, len(set))
	for cell := range set {
		out = append(out, cell)
	}
	return out
}
