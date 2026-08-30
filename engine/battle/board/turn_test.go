package board

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func turnBoard(t *testing.T, phase battle.Faction, turn int, units ...battle.Unit) *Board {
	t.Helper()
	bounds := battle.Bounds{{0, 0}, {5, 4}}
	board := &Board{state: battle.BattleState{
		Bounds: &bounds, Units: units, Phase: phase, Turn: turn}}
	if err := validate(&board.state); err != nil {
		t.Fatal(err)
	}
	return board
}

func basicUnit(id string, faction battle.Faction, x, y int) battle.Unit {
	return battle.Unit{
		ID: id, Faction: faction,
		Pos: battle.Cell{x, y}, Size: battle.Cell{1, 1},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140,
		Mech: battle.Mech{MoveRange: 1}, Pilot: battle.Pilot{},
	}
}

func armed(id string, faction battle.Faction, x, y int) battle.Unit {
	out := basicUnit(id, faction, x, y)
	out.Mech.Weapons = []battle.Weapon{{Name: "gun", Power: 5000, RangeMin: 1, RangeMax: 3, Accuracy: 100, UsableAfterMove: true}}
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func standby(id string) engagement.Decision {
	return engagement.Decision{UnitID: id, Kind: engagement.ActionStandby}
}

func pendingOf(b *Board) []*battle.Unit {
	return turn.Pending(&b.state, b.state.Phase)
}

func targetsOf(b *Board, unit *battle.Unit) []*battle.Unit {
	var out []*battle.Unit
	for index := range b.state.Units {
		other := &b.state.Units[index]
		if other.Faction == unit.Faction.Opposing() && other.Alive() {
			out = append(out, other)
		}
	}
	return out
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, basicUnit("a1", battle.FactionAlly, 1, 1), basicUnit("a2", battle.FactionAlly, 1, 2), basicUnit("e1", battle.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("a1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(resolution.Rotations) != 0 || board.state.Phase != battle.FactionAlly || board.state.Turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", resolution.Rotations, board.state.Turn, board.state.Phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, basicUnit("a1", battle.FactionAlly, 1, 1), basicUnit("e1", battle.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("a1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []turn.Rotation{{Turn: 1, Phase: battle.FactionThirdParty}, {Turn: 1, Phase: battle.FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.state.Phase != battle.FactionEnemy || board.state.Turn != 1 {
		t.Fatalf("turn %d phase %s", board.state.Turn, board.state.Phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := basicUnit("a1", battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	board := turnBoard(t, battle.FactionEnemy, 1, ally, basicUnit("e1", battle.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("e1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(resolution.Rotations, []turn.Rotation{{Turn: 2, Phase: battle.FactionAlly}}) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	got := board.state.Unit("a1")
	if got.Acted || got.EN != 140 {
		t.Fatalf("the phase start must reset the activation and cap the regeneration: %+v", got)
	}
	if enemy := board.state.Unit("e1"); !enemy.Acted || enemy.EN != 100 {
		t.Fatalf("the enemy side must keep its state until its own phase start: %+v", enemy)
	}
}

func TestThePhaseStartRegeneratesTenPercentOfTheMaximumFloored(t *testing.T) {
	ally := basicUnit("a1", battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	board := turnBoard(t, battle.FactionEnemy, 1, ally, basicUnit("e1", battle.FactionEnemy, 4, 4))

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.state.Unit("a1").EN; got != 61 {
		t.Fatalf("EN: %d, want 10 + floor(51.3)", got)
	}
}

func TestADebuffExpiresWhenItsRoundEnds(t *testing.T) {
	ally := basicUnit("a1", battle.FactionAlly, 1, 1)
	ally.Acted = true
	ally.Debuffs = []battle.Debuff{
		{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3},
		{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4},
	}
	enemy := basicUnit("e1", battle.FactionEnemy, 4, 4)
	enemy.Debuffs = []battle.Debuff{{Kind: "defense", Magnitude: 0.3, AppliedPhase: 3}}
	board := turnBoard(t, battle.FactionEnemy, 1, ally, enemy)

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.state.Unit("a1").Debuffs; !reflect.DeepEqual(got, []battle.Debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := board.state.Unit("e1").Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	board := turnBoard(t, battle.FactionEnemy, 2, basicUnit("e1", battle.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("e1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []turn.Rotation{{Turn: 3, Phase: battle.FactionAlly}, {Turn: 3, Phase: battle.FactionThirdParty}, {Turn: 3, Phase: battle.FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.state.Unit("e1").Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, basicUnit("a1", battle.FactionAlly, 1, 1), basicUnit("e1", battle.FactionEnemy, 4, 4))

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.state.Phase != battle.FactionAlly || board.state.Unit("a1").Acted {
		t.Fatal("the board changed on a refusal")
	}
}

func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, armed("a1", battle.FactionAlly, 1, 1), armed("a2", battle.FactionAlly, 1, 2), armed("e1", battle.FactionEnemy, 2, 1))
	dice := battle.Forced{AttackerSupport: true, DefenderSupport: true, Strike: true, Counter: true}

	for acts := 0; len(turn.Gone(&board.state)) == 0; acts++ {
		if acts > 100 {
			t.Fatal("no side is gone after 100 activations")
		}
		actor := pendingOf(board)[0]
		targets := targetsOf(board, actor)
		action := standby(actor.ID)
		if len(targets) > 0 {
			action = engagement.Decision{UnitID: actor.ID, Kind: engagement.ActionAttack,
				TargetID: targets[0].ID, Weapon: "gun",
				Response: &engagement.Response{Stance: engagement.StanceNone}}
		}
		if _, err := board.act(action, dice); err != nil {
			t.Fatalf("act %d: %v", acts, err)
		}
	}
}
