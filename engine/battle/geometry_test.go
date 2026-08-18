package battle

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func unit(id string, faction protocol.Faction, pos protocol.Cell) protocol.Unit {
	return protocol.Unit{UnitID: id, Faction: faction, Pos: pos, HP: 100, MaxHP: 100}
}

func board(units ...protocol.Unit) *protocol.BattleState {
	bounds := protocol.Bounds{{0, 0}, {4, 4}}
	return &protocol.BattleState{
		Units:  units,
		Phase:  protocol.FactionAlly,
		Turn:   1,
		Bounds: &bounds,
	}
}

func ids(units []*protocol.Unit) []string {
	out := make([]string, 0, len(units))
	for _, one := range units {
		out = append(out, one.UnitID)
	}
	return out
}

func TestADiagonalNeighbourIsTwoStepsAway(t *testing.T) {
	if got := Distance(protocol.Cell{2, 2}, protocol.Cell{3, 3}); got != 2 {
		t.Fatalf("diagonal distance: %d", got)
	}
	if got := Distance(protocol.Cell{2, 2}, protocol.Cell{2, 3}); got != 1 {
		t.Fatalf("orthogonal distance: %d", got)
	}
	if got := Distance(protocol.Cell{4, 1}, protocol.Cell{1, 3}); got != 5 {
		t.Fatalf("distance: %d", got)
	}
}

func TestARangeOneBandDoesNotHoldADiagonalNeighbour(t *testing.T) {
	weapon := protocol.Weapon{Name: "melee", RangeMin: 1, RangeMax: 1}

	if InBand(Distance(protocol.Cell{2, 2}, protocol.Cell{3, 3}), &weapon) {
		t.Fatal("a diagonal neighbour is at distance 2 and is out of the band")
	}
	if !InBand(Distance(protocol.Cell{2, 2}, protocol.Cell{3, 2}), &weapon) {
		t.Fatal("an orthogonal neighbour is in the band")
	}
	if InBand(0, &weapon) {
		t.Fatal("the cell of the unit itself is under the band")
	}
}

func TestReachIsTheDiamondOfTheMoveRange(t *testing.T) {
	state := &protocol.BattleState{Units: []protocol.Unit{unit("a1", protocol.FactionAlly, protocol.Cell{2, 2})}}
	state.Units[0].MoveRange = 2

	cells := ReachableCells(state, &state.Units[0])

	if len(cells) != 13 {
		t.Fatalf("cells: %d, against the 13 of the diamond", len(cells))
	}

	state.Units[0].MoveRange = 1
	near := ReachableCells(state, &state.Units[0])

	if len(near) != 5 {
		t.Fatalf("cells: %d, against the 5 of the diamond", len(near))
	}
	if near[protocol.Cell{3, 3}] {
		t.Fatal("a diagonal cell costs two steps, and this unit holds one")
	}
}

func TestReachDropsTheCellsBehindABlocker(t *testing.T) {
	state := board(
		unit("a1", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("e1", protocol.FactionEnemy, protocol.Cell{2, 3}),
	)
	state.Units[0].MoveRange = 2

	cells := SortedCells(ReachableCells(state, &state.Units[0]), state.Units[0].Pos)

	want := []protocol.Cell{
		{2, 2},
		{1, 2}, {2, 1}, {3, 2},
		{1, 1}, {1, 3}, {3, 1}, {3, 3},
		{0, 2}, {2, 0}, {4, 2},
	}
	if !reflect.DeepEqual(cells, want) {
		t.Fatalf("cells: %v", cells)
	}
}

func TestAnAllyLetsThePathThroughAndKeepsItsCell(t *testing.T) {
	state := board(
		unit("a1", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("a2", protocol.FactionAlly, protocol.Cell{2, 3}),
	)
	state.Units[0].MoveRange = 2

	cells := ReachableCells(state, &state.Units[0])

	if cells[protocol.Cell{2, 3}] {
		t.Fatal("the cell of the ally holds a unit and is no destination")
	}
	if !cells[protocol.Cell{2, 4}] {
		t.Fatal("the path through the ally is open")
	}
	if len(cells) != 12 {
		t.Fatalf("cells: %d", len(cells))
	}
}

func TestAThirdPartyBlocksThePathOfAnAlly(t *testing.T) {
	state := board(
		unit("a1", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("t1", protocol.FactionThirdParty, protocol.Cell{2, 3}),
	)
	state.Units[0].MoveRange = 2

	cells := ReachableCells(state, &state.Units[0])

	if cells[protocol.Cell{2, 4}] {
		t.Fatal("a unit of another faction blocks the path")
	}
}

func TestReachStopsAtTheBoardBounds(t *testing.T) {
	state := board(unit("a1", protocol.FactionAlly, protocol.Cell{0, 0}))
	state.Units[0].MoveRange = 1

	cells := ReachableCells(state, &state.Units[0])

	want := []protocol.Cell{{0, 0}, {0, 1}, {1, 0}}
	if got := SortedCells(cells, state.Units[0].Pos); !reflect.DeepEqual(got, want) {
		t.Fatalf("cells: %v", got)
	}
}

func TestReachOfTakesTheBoardRuleOfTheCaller(t *testing.T) {
	state := board(unit("a1", protocol.FactionAlly, protocol.Cell{2, 2}))
	state.Units[0].MoveRange = 1
	fixed := func(*protocol.BattleState, *protocol.Unit) CellSet {
		return CellSet{{0, 0}: true}
	}

	if got := ReachOf(state, &state.Units[0], fixed); !got[protocol.Cell{0, 0}] || len(got) != 1 {
		t.Fatalf("cells: %v", got)
	}
	if got := ReachOf(state, &state.Units[0], nil); len(got) != 5 {
		t.Fatalf("cells: %v", got)
	}
}

func TestNearestFreeCellSearchesOnTheOrthogonalSteps(t *testing.T) {
	taken := CellSet{{0, 0}: true}

	if got := NearestFreeCell(protocol.Cell{0, 0}, taken); got != (protocol.Cell{-1, 0}) {
		t.Fatalf("first free cell: %v", got)
	}

	for _, cell := range []protocol.Cell{{-1, 0}, {0, -1}, {0, 1}, {1, 0}} {
		taken[cell] = true
	}

	if got := NearestFreeCell(protocol.Cell{0, 0}, taken); got != (protocol.Cell{-2, 0}) {
		t.Fatalf("the search leaves the ring on a step of the board, not on a diagonal: %v", got)
	}
}

func TestBlastVictimsAreTheLiveFoesInTheBand(t *testing.T) {
	state := board(
		unit("a1", protocol.FactionAlly, protocol.Cell{0, 0}),
		unit("e_diagonal", protocol.FactionEnemy, protocol.Cell{3, 3}),
		unit("e_side", protocol.FactionEnemy, protocol.Cell{2, 3}),
		unit("e_centre", protocol.FactionEnemy, protocol.Cell{2, 2}),
		unit("e_dead", protocol.FactionEnemy, protocol.Cell{1, 2}),
		unit("a2", protocol.FactionAlly, protocol.Cell{2, 1}),
	)
	state.Units[4].HP = 0
	weapon := protocol.Weapon{Name: "blast", Blast: 1}

	victims := BlastVictims(state, &state.Units[0], &weapon, protocol.Cell{2, 2})

	if got := ids(victims); !reflect.DeepEqual(got, []string{"e_side", "e_centre"}) {
		t.Fatalf("victims: %v", got)
	}
}

func TestTargetsOfAnswersTheOpposingFaction(t *testing.T) {
	state := board(
		unit("a1", protocol.FactionAlly, protocol.Cell{0, 0}),
		unit("e1", protocol.FactionEnemy, protocol.Cell{1, 0}),
		unit("t1", protocol.FactionThirdParty, protocol.Cell{2, 0}),
	)

	if got := ids(TargetsOf(state, &state.Units[0])); !reflect.DeepEqual(got, []string{"e1"}) {
		t.Fatalf("targets of the ally: %v", got)
	}
	if got := ids(TargetsOf(state, &state.Units[1])); !reflect.DeepEqual(got, []string{"a1"}) {
		t.Fatalf("targets of the enemy: %v", got)
	}
	if got := ids(TargetsOf(state, &state.Units[2])); !reflect.DeepEqual(got, []string{"a1"}) {
		t.Fatalf("targets of the third party: %v", got)
	}
}

func TestSupportDefenderNeedsAChargeAndTheBoardDistance(t *testing.T) {
	state := board(
		unit("defender", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("diagonal", protocol.FactionAlly, protocol.Cell{3, 3}),
		unit("spent", protocol.FactionAlly, protocol.Cell{2, 1}),
		unit("enemy", protocol.FactionEnemy, protocol.Cell{1, 2}),
		unit("ready", protocol.FactionAlly, protocol.Cell{3, 2}),
	)
	for index := 1; index < len(state.Units); index++ {
		state.Units[index].MoveRange = 1
		state.Units[index].SupportDefendCharges = 1
	}
	state.Units[2].SupportDefendCharges = 0

	found := FindSupportDefender(state, &state.Units[0])

	if found == nil || found.UnitID != "ready" {
		t.Fatalf("defender: %v", found)
	}
}

func TestAttackShieldNeedsTheShieldFlag(t *testing.T) {
	state := board(
		unit("attacker", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("plain", protocol.FactionAlly, protocol.Cell{2, 1}),
		unit("shield", protocol.FactionAlly, protocol.Cell{2, 3}),
	)
	for index := 1; index < len(state.Units); index++ {
		state.Units[index].MoveRange = 1
		state.Units[index].SupportDefendCharges = 1
	}
	state.Units[2].AttackShield = true

	found := FindAttackShield(state, &state.Units[0])

	if found == nil || found.UnitID != "shield" {
		t.Fatalf("shield bearer: %v", found)
	}
}

func TestSupportAttackersAnswerInRosterOrder(t *testing.T) {
	rifle := protocol.Weapon{Name: "rifle", RangeMin: 1, RangeMax: 2}
	scatter := protocol.Weapon{Name: "scatter", RangeMin: 1, RangeMax: 3, MapWeapon: true}
	state := board(
		unit("lead", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("south", protocol.FactionAlly, protocol.Cell{2, 3}),
		unit("north", protocol.FactionAlly, protocol.Cell{2, 1}),
		unit("diagonal", protocol.FactionAlly, protocol.Cell{1, 1}),
		unit("spent", protocol.FactionAlly, protocol.Cell{1, 2}),
		unit("foe", protocol.FactionEnemy, protocol.Cell{3, 2}),
	)
	for index := 1; index < len(state.Units); index++ {
		state.Units[index].MoveRange = 1
		state.Units[index].SupportAttackCharges = 1
		state.Units[index].Weapons = []protocol.Weapon{scatter, rifle}
	}
	state.Units[4].SupportAttackCharges = 0

	volley := FindSupportAttackers(state, &state.Units[0], &state.Units[5], nil)

	if len(volley) != 2 {
		t.Fatalf("volley: %v", volley)
	}
	if volley[0].Unit.UnitID != "south" || volley[1].Unit.UnitID != "north" {
		t.Fatalf("the order follows the roster, not the board: %s, %s",
			volley[0].Unit.UnitID, volley[1].Unit.UnitID)
	}
	if Distance(volley[0].Unit.Pos, state.Units[5].Pos) != Distance(volley[1].Unit.Pos, state.Units[5].Pos) {
		t.Fatal("the case must hold two attackers at an equal distance")
	}
	if volley[0].Weapon.Name != "rifle" {
		t.Fatalf("a map weapon does not support: %s", volley[0].Weapon.Name)
	}
}

func TestSupportAttackersReadTheCellOfTheRequest(t *testing.T) {
	state := board(
		unit("lead", protocol.FactionAlly, protocol.Cell{2, 2}),
		unit("south", protocol.FactionAlly, protocol.Cell{2, 3}),
		unit("foe", protocol.FactionEnemy, protocol.Cell{3, 2}),
	)
	state.Units[1].MoveRange = 1
	state.Units[1].SupportAttackCharges = 1
	state.Units[1].Weapons = []protocol.Weapon{{Name: "rifle", RangeMin: 1, RangeMax: 2}}
	away := protocol.Cell{0, 0}

	if got := FindSupportAttackers(state, &state.Units[0], &state.Units[2], &away); got != nil {
		t.Fatalf("the foe cell of the request is out of the band: %v", got)
	}
}

func TestProximityRanksTheDistanceFirstAndTheCellLast(t *testing.T) {
	anchor := protocol.Cell{2, 2}

	if !Proximity(protocol.Cell{2, 3}, anchor).Less(Proximity(protocol.Cell{3, 3}, anchor)) {
		t.Fatal("the diagonal cell is farther on the board")
	}
	if !Proximity(protocol.Cell{1, 1}, anchor).Less(Proximity(protocol.Cell{0, 2}, anchor)) {
		t.Fatal("an equal board distance ranks on the straight line")
	}
	if !Proximity(protocol.Cell{1, 3}, anchor).Less(Proximity(protocol.Cell{3, 1}, anchor)) {
		t.Fatal("an equal straight line ranks on the cell")
	}
}
