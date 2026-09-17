package system

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func turnPair(phase battle.Faction, turn int, units ...battle.Unit) (state.Content, state.Values) {
	bounds := battle.Bounds{{0, 0}, {5, 4}}
	return assembled(battle.BattleState{Bounds: &bounds, Units: units,
		Phase: phase, Turn: turn})
}

func turnBoard(phase battle.Faction, turn int, units ...battle.Unit) state.Battle {
	content, values := turnPair(phase, turn, units...)
	return state.Battle{Content: &content, Values: &values}
}

type phaseOf struct {
	turn  int
	phase battle.Faction
}

func phasesOf(events []battle.PhaseEvent) []phaseOf {
	out := make([]phaseOf, 0, len(events))
	for _, event := range events {
		out = append(out, phaseOf{event.Turn, event.Phase})
	}
	return out
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
	board.Values.Units[0].HP = 0
	if got := Gone(board); !reflect.DeepEqual(got, []battle.Faction{battle.FactionAlly, battle.FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := basicUnit(battle.FactionAlly, 1, 1)
	content, values := turnPair(battle.FactionAlly, 1, last)
	values.Units[0].HP = 0

	got := rotate(state.Battle{Content: &content, Values: &values})
	after := values

	if len(got) != 0 || after.Phase != battle.FactionAlly || after.Turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	acted := basicUnit(battle.FactionAlly, 1, 1)
	acted.Acted = true
	content, values := turnPair(battle.FactionAlly, 1, acted,
		basicUnit(battle.FactionAlly, 1, 2), basicUnit(battle.FactionEnemy, 4, 4))

	got := rotate(state.Battle{Content: &content, Values: &values})
	after := values

	if len(got) != 0 || after.Phase != battle.FactionAlly || after.Turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", got, after.Turn, after.Phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	acted := basicUnit(battle.FactionAlly, 1, 1)
	acted.Acted = true
	content, values := turnPair(battle.FactionAlly, 1, acted, basicUnit(battle.FactionEnemy, 4, 4))

	got := rotate(state.Battle{Content: &content, Values: &values})
	after := values

	want := []phaseOf{{1, battle.FactionThirdParty}, {1, battle.FactionEnemy}}
	if !reflect.DeepEqual(phasesOf(got), want) {
		t.Fatalf("rotations: %+v", got)
	}
	if after.Phase != battle.FactionEnemy || after.Turn != 1 {
		t.Fatalf("turn %d phase %s", after.Turn, after.Phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := basicUnit(battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	content, values := turnPair(battle.FactionEnemy, 1, ally, enemy)

	rotations := rotate(state.Battle{Content: &content, Values: &values})
	after := values

	if !reflect.DeepEqual(phasesOf(rotations), []phaseOf{{2, battle.FactionAlly}}) {
		t.Fatalf("rotations: %+v", rotations)
	}
	allyUnit := &after.Units[0]
	if allyUnit.Acted || allyUnit.EN != 140 {
		t.Fatalf("the phase start must reset the activation and cap the regeneration: %+v", allyUnit)
	}
	if enemyUnit := &after.Units[1]; !enemyUnit.Acted || enemyUnit.EN != 100 {
		t.Fatalf("the enemy side must keep its state until its own phase start: %+v", enemyUnit)
	}
}

func TestThePhaseStartRegeneratesTenPercentOfTheMaximumFloored(t *testing.T) {
	ally := basicUnit(battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	content, values := turnPair(battle.FactionEnemy, 1, ally, enemy)

	rotate(state.Battle{Content: &content, Values: &values})
	after := values

	if got := after.Units[0].EN; got != 61 {
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
	content, values := turnPair(battle.FactionEnemy, 1, ally, enemy)

	rotate(state.Battle{Content: &content, Values: &values})
	after := values

	if got := after.Units[0].Debuffs; !reflect.DeepEqual(got, []battle.Debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := after.Units[1].Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	enemy := basicUnit(battle.FactionEnemy, 4, 4)
	enemy.Acted = true
	content, values := turnPair(battle.FactionEnemy, 2, enemy)

	got := rotate(state.Battle{Content: &content, Values: &values})
	after := values

	want := []phaseOf{{3, battle.FactionAlly}, {3, battle.FactionThirdParty}, {3, battle.FactionEnemy}}
	if !reflect.DeepEqual(phasesOf(got), want) {
		t.Fatalf("rotations: %+v", got)
	}
	if after.Units[0].Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}

// The rotation reads a pair alone. No engagement runs before it, and the pair
// below comes from no conversion.
func TestTheRotationRunsOnAPairThatNoEngagementProduced(t *testing.T) {
	content := state.Content{
		Units: []state.UnitContent{
			{Faction: battle.FactionAlly, Size: battle.Cell{1, 1}, MaxHP: 100, ENMax: 140,
				Mech: &def.Mech{MoveRange: 1}, Pilot: &def.Pilot{}},
			{Faction: battle.FactionEnemy, Size: battle.Cell{1, 1}, MaxHP: 100, ENMax: 140,
				Mech: &def.Mech{MoveRange: 1}, Pilot: &def.Pilot{}},
		},
		Bounds: battle.Bounds{{0, 0}, {5, 4}},
	}
	values := state.Values{
		Units: []state.UnitValue{
			{Pos: battle.Cell{1, 1}, HP: 100, EN: 100, Acted: true},
			{Pos: battle.Cell{4, 4}, HP: 100, EN: 100},
		},
		Phase: battle.FactionAlly,
		Turn:  1,
	}

	rotations := rotate(state.Battle{Content: &content, Values: &values})
	after := values

	want := []phaseOf{{1, battle.FactionThirdParty}, {1, battle.FactionEnemy}}
	if !reflect.DeepEqual(phasesOf(rotations), want) {
		t.Fatalf("rotations: %+v", rotations)
	}
	if after.Phase != battle.FactionEnemy || after.Turn != 1 || after.Units[1].Acted {
		t.Fatalf("values: %+v", after)
	}
}
