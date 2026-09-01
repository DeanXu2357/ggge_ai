package turn

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func turnBoard(phase battle.Faction, turn int, units ...battle.Unit) *state.Battle {
	bounds := battle.Bounds{{0, 0}, {5, 4}}
	out := state.FromContract(battle.BattleState{Bounds: &bounds, Units: units,
		Phase: phase, Turn: turn})
	return &out
}

func basicUnit(faction battle.Faction, x, y int) battle.Unit {
	return battle.Unit{
		Faction: faction,
		Pos:     battle.Cell{x, y}, Size: battle.Cell{1, 1},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140,
		Mech: battle.Mech{MoveRange: 1}, Pilot: battle.Pilot{},
	}
}

func TestPendingHoldsTheLivingUnitsOfTheSideThatDidNotAct(t *testing.T) {
	acted := basicUnit(battle.FactionAlly, 1, 2)
	acted.Acted = true
	dead := basicUnit(battle.FactionAlly, 1, 3)
	dead.HP = 0
	board := turnBoard(battle.FactionAlly, 1, basicUnit(battle.FactionAlly, 1, 1), acted, dead, basicUnit(battle.FactionEnemy, 4, 4))

	if ids := Pending(board, battle.FactionAlly); !reflect.DeepEqual(ids, []int{0}) {
		t.Fatalf("pending: %v", ids)
	}
}

func TestGoneNamesTheSidesWithNoLivingUnit(t *testing.T) {
	dead := basicUnit(battle.FactionEnemy, 4, 4)
	dead.HP = 0
	board := turnBoard(battle.FactionAlly, 1, basicUnit(battle.FactionAlly, 1, 1), dead)

	if got := Gone(board); !reflect.DeepEqual(got, []battle.Faction{battle.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
	board.Units[0].Value.HP = 0
	if got := Gone(board); !reflect.DeepEqual(got, []battle.Faction{battle.FactionAlly, battle.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := basicUnit(battle.FactionAlly, 1, 1)
	board := turnBoard(battle.FactionAlly, 1, last)
	board.Units[0].Value.HP = 0

	if got := Advance(board); len(got) != 0 || board.Phase != battle.FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	acted := basicUnit(battle.FactionAlly, 1, 1)
	acted.Acted = true
	board := turnBoard(battle.FactionAlly, 1, acted, basicUnit(battle.FactionAlly, 1, 2), basicUnit(battle.FactionEnemy, 4, 4))

	if got := Advance(board); len(got) != 0 || board.Phase != battle.FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", got, board.Turn, board.Phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	acted := basicUnit(battle.FactionAlly, 1, 1)
	acted.Acted = true
	board := turnBoard(battle.FactionAlly, 1, acted, basicUnit(battle.FactionEnemy, 4, 4))

	want := []Rotation{{Turn: 1, Phase: battle.FactionThirdParty}, {Turn: 1, Phase: battle.FactionEnemy}}
	if got := Advance(board); !reflect.DeepEqual(got, want) {
		t.Fatalf("rotations: %+v", got)
	}
	if board.Phase != battle.FactionEnemy || board.Turn != 1 {
		t.Fatalf("turn %d phase %s", board.Turn, board.Phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := basicUnit(battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	board := turnBoard(battle.FactionEnemy, 1, ally, enemy)

	rotations := Advance(board)
	if !reflect.DeepEqual(rotations, []Rotation{{Turn: 2, Phase: battle.FactionAlly}}) {
		t.Fatalf("rotations: %+v", rotations)
	}
	allyUnit := &board.Units[0]
	if allyUnit.Value.Acted || allyUnit.Value.EN != 140 {
		t.Fatalf("the phase start must reset the activation and cap the regeneration: %+v", allyUnit)
	}
	if enemyUnit := &board.Units[1]; !enemyUnit.Value.Acted || enemyUnit.Value.EN != 100 {
		t.Fatalf("the enemy side must keep its state until its own phase start: %+v", enemyUnit)
	}
}

func TestThePhaseStartRegeneratesTenPercentOfTheMaximumFloored(t *testing.T) {
	ally := basicUnit(battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	board := turnBoard(battle.FactionEnemy, 1, ally, enemy)

	Advance(board)
	if got := board.Units[0].Value.EN; got != 61 {
		t.Fatalf("EN: %d, want 10 + floor(51.3)", got)
	}
}

func TestADebuffExpiresWhenItsRoundEnds(t *testing.T) {
	ally := basicUnit(battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.Debuffs = []battle.Debuff{
		{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3},
		{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4},
	}
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	enemy.Debuffs = []battle.Debuff{{Kind: "defense", Magnitude: 0.3, AppliedPhase: 3}}
	board := turnBoard(battle.FactionEnemy, 1, ally, enemy)

	Advance(board)
	if got := board.Units[0].Value.Debuffs; !reflect.DeepEqual(got, []battle.Debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := board.Units[1].Value.Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	board := turnBoard(battle.FactionEnemy, 2, enemy)

	want := []Rotation{{Turn: 3, Phase: battle.FactionAlly}, {Turn: 3, Phase: battle.FactionThirdParty}, {Turn: 3, Phase: battle.FactionEnemy}}
	if got := Advance(board); !reflect.DeepEqual(got, want) {
		t.Fatalf("rotations: %+v", got)
	}
	if board.Units[0].Value.Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}
