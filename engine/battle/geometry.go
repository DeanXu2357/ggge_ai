// Package battle holds the board rules of the engine. The authority is
// 'src/ggge_ai/sandbox/model.py', with one correction: the game moves and
// measures range on the four orthogonal steps, and the Python module keeps the
// eight king steps. The Python side gets no corrected version (ruling
// 2026-08-18, issue #61), so a result that depends on the distance differs
// between the two sides by design.
package battle

import (
	"sort"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// The steps hold the orthogonal subset of the king steps of the model, in the
// order of the model. The order decides the outward search of NearestFreeCell.
var steps = [4]protocol.Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}}

type CellSet map[protocol.Cell]bool

// A ReachFn answers the cells that one unit can move to. A caller that holds a
// board rule of its own passes its own function to ReachOf.
type ReachFn func(*protocol.BattleState, *protocol.Unit) CellSet

// A SupportShot is one support attacker with the weapon that it fires.
type SupportShot struct {
	Unit   *protocol.Unit
	Weapon *protocol.Weapon
}

func Alive(unit *protocol.Unit) bool {
	return unit.HP > 0
}

// Find gives the unit of the board, not a copy: the rules of this package read
// the identity of a unit, as the model reads it.
func Find(state *protocol.BattleState, unitID string) *protocol.Unit {
	for index := range state.Units {
		if state.Units[index].UnitID == unitID {
			return &state.Units[index]
		}
	}
	return nil
}

func Distance(a, b protocol.Cell) int {
	return abs(a[0]-b[0]) + abs(a[1]-b[1])
}

func InBand(distance int, weapon *protocol.Weapon) bool {
	return weapon.RangeMin <= distance && distance <= weapon.RangeMax
}

// BlockingCells holds the cells that stop a path of the unit. An ally does not
// stop a path; it only denies its own cell as a destination (OccupiedCells).
func BlockingCells(state *protocol.BattleState, unit *protocol.Unit) CellSet {
	out := CellSet{}
	for index := range state.Units {
		other := &state.Units[index]
		if other == unit || !Alive(other) || other.Faction == unit.Faction {
			continue
		}
		out[other.Pos] = true
	}
	return out
}

// OccupiedCells holds the cells that no unit can end its move on.
func OccupiedCells(state *protocol.BattleState, unit *protocol.Unit) CellSet {
	out := CellSet{}
	for index := range state.Units {
		other := &state.Units[index]
		if other == unit || !Alive(other) {
			continue
		}
		out[other.Pos] = true
	}
	return out
}

func InBounds(state *protocol.BattleState, cell protocol.Cell) bool {
	if state.Bounds == nil {
		return true
	}
	low, high := state.Bounds[0], state.Bounds[1]
	return low[0] <= cell[0] && cell[0] <= high[0] && low[1] <= cell[1] && cell[1] <= high[1]
}

// ReachableCells spends one point of the move range on each step. A cell on a
// diagonal costs two.
func ReachableCells(state *protocol.BattleState, unit *protocol.Unit) CellSet {
	blocked := BlockingCells(state, unit)
	occupied := OccupiedCells(state, unit)
	seen := CellSet{unit.Pos: true}
	out := CellSet{unit.Pos: true}
	frontier := []walk{{unit.Pos, 0}}
	for len(frontier) > 0 {
		step := frontier[0]
		frontier = frontier[1:]
		if step.spent == unit.MoveRange {
			continue
		}
		for _, delta := range steps {
			next := protocol.Cell{step.cell[0] + delta[0], step.cell[1] + delta[1]}
			if seen[next] || blocked[next] || !InBounds(state, next) {
				continue
			}
			seen[next] = true
			frontier = append(frontier, walk{next, step.spent + 1})
			if !occupied[next] {
				out[next] = true
			}
		}
	}
	return out
}

type walk struct {
	cell  protocol.Cell
	spent int
}

// NearestFreeCell searches outward on the step set of the board. The board
// bounds do not hold it: the caller checks the answer against the bounds.
func NearestFreeCell(cell protocol.Cell, taken CellSet) protocol.Cell {
	seen := CellSet{cell: true}
	frontier := []protocol.Cell{cell}
	for len(frontier) > 0 {
		pos := frontier[0]
		frontier = frontier[1:]
		if !taken[pos] {
			return pos
		}
		for _, delta := range steps {
			next := protocol.Cell{pos[0] + delta[0], pos[1] + delta[1]}
			if !seen[next] {
				seen[next] = true
				frontier = append(frontier, next)
			}
		}
	}
	return cell
}

func ReachOf(state *protocol.BattleState, unit *protocol.Unit, reach ReachFn) CellSet {
	if reach == nil {
		reach = ReachableCells
	}
	return reach(state, unit)
}

func OpposingFaction(faction protocol.Faction) protocol.Faction {
	if faction == protocol.FactionAlly {
		return protocol.FactionEnemy
	}
	return protocol.FactionAlly
}

func TargetsOf(state *protocol.BattleState, unit *protocol.Unit) []*protocol.Unit {
	return ByFaction(state, OpposingFaction(unit.Faction))
}

func ByFaction(state *protocol.BattleState, faction protocol.Faction) []*protocol.Unit {
	var out []*protocol.Unit
	for index := range state.Units {
		other := &state.Units[index]
		if other.Faction == faction && Alive(other) {
			out = append(out, other)
		}
	}
	return out
}

func BlastVictims(
	state *protocol.BattleState,
	actor *protocol.Unit,
	weapon *protocol.Weapon,
	aim protocol.Cell,
) []*protocol.Unit {
	var out []*protocol.Unit
	for _, target := range TargetsOf(state, actor) {
		if Distance(target.Pos, aim) <= weapon.Blast {
			out = append(out, target)
		}
	}
	return out
}

func FindSupportDefender(state *protocol.BattleState, defender *protocol.Unit) *protocol.Unit {
	for index := range state.Units {
		other := &state.Units[index]
		if other == defender || !Alive(other) || other.Faction != defender.Faction {
			continue
		}
		if other.SupportDefendCharges <= 0 {
			continue
		}
		if Distance(other.Pos, defender.Pos) <= other.MoveRange {
			return other
		}
	}
	return nil
}

func FindAttackShield(state *protocol.BattleState, attacker *protocol.Unit) *protocol.Unit {
	for index := range state.Units {
		other := &state.Units[index]
		if other == attacker || !Alive(other) || other.Faction != attacker.Faction {
			continue
		}
		if !other.AttackShield || other.SupportDefendCharges <= 0 {
			continue
		}
		if Distance(other.Pos, attacker.Pos) <= other.MoveRange {
			return other
		}
	}
	return nil
}

// FindSupportAttackers answers in the order of the roster. The order decides
// who joins the engagement, so it is part of the contract.
func FindSupportAttackers(
	state *protocol.BattleState,
	supported *protocol.Unit,
	foe *protocol.Unit,
	foePos *protocol.Cell,
) []SupportShot {
	var out []SupportShot
	cell := foe.Pos
	if foePos != nil {
		cell = *foePos
	}
	for index := range state.Units {
		other := &state.Units[index]
		if other == supported || !Alive(other) || other.Faction != supported.Faction {
			continue
		}
		if other.SupportAttackCharges <= 0 {
			continue
		}
		if Distance(other.Pos, supported.Pos) > other.MoveRange {
			continue
		}
		distance := Distance(other.Pos, cell)
		for weaponIndex := range other.Weapons {
			weapon := &other.Weapons[weaponIndex]
			if !weapon.MapWeapon && other.EN >= weapon.ENCost && InBand(distance, weapon) {
				out = append(out, SupportShot{Unit: other, Weapon: weapon})
				break
			}
		}
	}
	return out
}

// A ProximityKey ranks a cell against an anchor: the board distance first, then
// the square of the straight line, then the cell itself.
type ProximityKey struct {
	Distance int
	Square   int
	Cell     protocol.Cell
}

func Proximity(cell, anchor protocol.Cell) ProximityKey {
	dx, dy := cell[0]-anchor[0], cell[1]-anchor[1]
	return ProximityKey{Distance: Distance(cell, anchor), Square: dx*dx + dy*dy, Cell: cell}
}

func (k ProximityKey) Less(other ProximityKey) bool {
	if k.Distance != other.Distance {
		return k.Distance < other.Distance
	}
	if k.Square != other.Square {
		return k.Square < other.Square
	}
	if k.Cell[0] != other.Cell[0] {
		return k.Cell[0] < other.Cell[0]
	}
	return k.Cell[1] < other.Cell[1]
}

// SortedCells gives the set as a list, nearest to the anchor first.
func SortedCells(set CellSet, anchor protocol.Cell) []protocol.Cell {
	out := make([]protocol.Cell, 0, len(set))
	for cell := range set {
		out = append(out, cell)
	}
	sort.Slice(out, func(i, j int) bool {
		return Proximity(out[i], anchor).Less(Proximity(out[j], anchor))
	})
	return out
}

func abs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}
