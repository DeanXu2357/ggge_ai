package board

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func turnBoard(t *testing.T, phase state.Faction, turn int, units ...state.Unit) *Board {
	t.Helper()
	board, err := newBoard(state.Bounds{High: state.Cell{5, 4}}, units)
	if err != nil {
		t.Fatal(err)
	}
	board.state.Phase = phase
	board.state.Turn = turn
	return board
}

func basicUnit(id string, faction state.Faction, x, y int) state.Unit {
	return state.Unit{
		ID: id, Faction: faction,
		Footprint: state.Footprint{Anchor: state.Cell{x, y}, Size: state.Size{1, 1}},
		HP:        100, MaxHP: 100, EN: 100, ENMax: 140,
		Mech: &def.Mech{MoveRange: 1}, Pilot: &def.Pilot{},
	}
}

func armed(id string, faction state.Faction, x, y int) state.Unit {
	out := basicUnit(id, faction, x, y)
	out.Mech.Weapons = []def.Weapon{{Name: "gun", Power: 5000, Range: def.RadiusRange{Min: 1, Max: 3}, Accuracy: 100, CanCounter: true, UsableAfterMove: true}}
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func standby(id string) engagement.Decision {
	return engagement.Decision{UnitID: id, Kind: engagement.ActionStandby}
}

func pendingOf(b *Board) []*state.Unit {
	return turn.Pending(&b.state, b.state.Phase)
}

func targetsOf(b *Board, unit *state.Unit) []*state.Unit {
	var out []*state.Unit
	for index := range b.state.Units {
		other := &b.state.Units[index]
		if other.Faction == unit.Faction.Opposing() && alive(other) {
			out = append(out, other)
		}
	}
	return out
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	board := turnBoard(t, state.FactionAlly, 1, basicUnit("a1", state.FactionAlly, 1, 1), basicUnit("a2", state.FactionAlly, 1, 2), basicUnit("e1", state.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("a1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(resolution.Rotations) != 0 || board.state.Phase != state.FactionAlly || board.state.Turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", resolution.Rotations, board.state.Turn, board.state.Phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	board := turnBoard(t, state.FactionAlly, 1, basicUnit("a1", state.FactionAlly, 1, 1), basicUnit("e1", state.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("a1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []turn.Rotation{{Turn: 1, Phase: state.FactionThirdParty}, {Turn: 1, Phase: state.FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.state.Phase != state.FactionEnemy || board.state.Turn != 1 {
		t.Fatalf("turn %d phase %s", board.state.Turn, board.state.Phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := basicUnit("a1", state.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	board := turnBoard(t, state.FactionEnemy, 1, ally, basicUnit("e1", state.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("e1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(resolution.Rotations, []turn.Rotation{{Turn: 2, Phase: state.FactionAlly}}) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	got := board.unit("a1")
	if got.Acted || got.EN != 140 {
		t.Fatalf("the phase start must reset the activation and cap the regeneration: %+v", got)
	}
	if enemy := board.unit("e1"); !enemy.Acted || enemy.EN != 100 {
		t.Fatalf("the enemy side must keep its state until its own phase start: %+v", enemy)
	}
}

func TestThePhaseStartRegeneratesTenPercentOfTheMaximumFloored(t *testing.T) {
	ally := basicUnit("a1", state.FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	board := turnBoard(t, state.FactionEnemy, 1, ally, basicUnit("e1", state.FactionEnemy, 4, 4))

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.unit("a1").EN; got != 61 {
		t.Fatalf("EN: %d, want 10 + floor(51.3)", got)
	}
}

func TestADebuffExpiresWhenItsRoundEnds(t *testing.T) {
	ally := basicUnit("a1", state.FactionAlly, 1, 1)
	ally.Acted = true
	ally.Debuffs = []state.Debuff{
		{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3},
		{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4},
	}
	enemy := basicUnit("e1", state.FactionEnemy, 4, 4)
	enemy.Debuffs = []state.Debuff{{Kind: "defense", Magnitude: 0.3, AppliedPhase: 3}}
	board := turnBoard(t, state.FactionEnemy, 1, ally, enemy)

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.unit("a1").Debuffs; !reflect.DeepEqual(got, []state.Debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := board.unit("e1").Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	board := turnBoard(t, state.FactionEnemy, 2, basicUnit("e1", state.FactionEnemy, 4, 4))

	resolution, err := board.act(standby("e1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []turn.Rotation{{Turn: 3, Phase: state.FactionAlly}, {Turn: 3, Phase: state.FactionThirdParty}, {Turn: 3, Phase: state.FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.unit("e1").Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, state.FactionAlly, 1, basicUnit("a1", state.FactionAlly, 1, 1), basicUnit("e1", state.FactionEnemy, 4, 4))

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.state.Phase != state.FactionAlly || board.unit("a1").Acted {
		t.Fatal("the board changed on a refusal")
	}
}

func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, state.FactionAlly, 1, armed("a1", state.FactionAlly, 1, 1), armed("a2", state.FactionAlly, 1, 2), armed("e1", state.FactionEnemy, 2, 1))
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
