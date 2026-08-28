package board

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func turnBoard(t *testing.T, phase faction, turn int, units ...unit) *Board {
	t.Helper()
	board, err := newBoard(bounds{High: cell{5, 4}}, units)
	if err != nil {
		t.Fatal(err)
	}
	board.phase = phase
	board.turn = turn
	return board
}

func basicUnit(id string, faction faction, x, y int) unit {
	return unit{
		ID: id, Faction: faction, Footprint: footprint{Anchor: cell{x, y}, Size: size{1, 1}},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140, Mech: mech{MoveRange: 1},
	}
}

func armed(id string, faction faction, x, y int) unit {
	out := basicUnit(id, faction, x, y)
	out.Mech.Weapons = []weapon{{Name: "gun", Power: 5000, Range: radiusRange{Min: 1, Max: 3}, Accuracy: 100, CanCounter: true, UsableAfterMove: true}}
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func standby(id string) decision {
	return decision{UnitID: id, Kind: actionStandby}
}

func TestPendingHoldsTheLivingUnitsOfTheSideThatDidNotAct(t *testing.T) {
	acted := basicUnit("a2", factionAlly, 1, 2)
	acted.Acted = true
	dead := basicUnit("a3", factionAlly, 1, 3)
	dead.HP = 0
	board := turnBoard(t, factionAlly, 1, basicUnit("a1", factionAlly, 1, 1), acted, dead, basicUnit("e1", factionEnemy, 4, 4))

	var ids []string
	for _, pending := range board.pending(factionAlly) {
		ids = append(ids, pending.ID)
	}
	if !reflect.DeepEqual(ids, []string{"a1"}) {
		t.Fatalf("pending: %v", ids)
	}
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	board := turnBoard(t, factionAlly, 1, basicUnit("a1", factionAlly, 1, 1), basicUnit("a2", factionAlly, 1, 2), basicUnit("e1", factionEnemy, 4, 4))

	resolution, err := board.act(standby("a1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(resolution.Rotations) != 0 || board.phase != factionAlly || board.turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", resolution.Rotations, board.turn, board.phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	board := turnBoard(t, factionAlly, 1, basicUnit("a1", factionAlly, 1, 1), basicUnit("e1", factionEnemy, 4, 4))

	resolution, err := board.act(standby("a1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []rotation{{Turn: 1, Phase: factionThirdParty}, {Turn: 1, Phase: factionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.phase != factionEnemy || board.turn != 1 {
		t.Fatalf("turn %d phase %s", board.turn, board.phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := basicUnit("a1", factionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	board := turnBoard(t, factionEnemy, 1, ally, basicUnit("e1", factionEnemy, 4, 4))

	resolution, err := board.act(standby("e1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(resolution.Rotations, []rotation{{Turn: 2, Phase: factionAlly}}) {
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
	ally := basicUnit("a1", factionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	board := turnBoard(t, factionEnemy, 1, ally, basicUnit("e1", factionEnemy, 4, 4))

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.unit("a1").EN; got != 61 {
		t.Fatalf("EN: %d, want 10 + floor(51.3)", got)
	}
}

func TestADebuffExpiresWhenItsRoundEnds(t *testing.T) {
	ally := basicUnit("a1", factionAlly, 1, 1)
	ally.Acted = true
	ally.Debuffs = []debuff{
		{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3},
		{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4},
	}
	enemy := basicUnit("e1", factionEnemy, 4, 4)
	enemy.Debuffs = []debuff{{Kind: "defense", Magnitude: 0.3, AppliedPhase: 3}}
	board := turnBoard(t, factionEnemy, 1, ally, enemy)

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.unit("a1").Debuffs; !reflect.DeepEqual(got, []debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := board.unit("e1").Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	board := turnBoard(t, factionEnemy, 2, basicUnit("e1", factionEnemy, 4, 4))

	resolution, err := board.act(standby("e1"), battle.NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []rotation{{Turn: 3, Phase: factionAlly}, {Turn: 3, Phase: factionThirdParty}, {Turn: 3, Phase: factionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.unit("e1").Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}

func TestGoneNamesTheSidesWithNoLivingUnit(t *testing.T) {
	dead := basicUnit("e1", factionEnemy, 4, 4)
	dead.HP = 0
	board := turnBoard(t, factionAlly, 1, basicUnit("a1", factionAlly, 1, 1), dead)

	if got := board.gone(); !reflect.DeepEqual(got, []faction{factionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
	board.unit("a1").HP = 0
	if got := board.gone(); !reflect.DeepEqual(got, []faction{factionAlly, factionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := basicUnit("a1", factionAlly, 1, 1)
	board := turnBoard(t, factionAlly, 1, last)
	board.unit("a1").HP = 0

	if got := board.Advance(); len(got) != 0 || board.phase != factionAlly || board.turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, factionAlly, 1, basicUnit("a1", factionAlly, 1, 1), basicUnit("e1", factionEnemy, 4, 4))

	if _, err := board.act(standby("e1"), battle.NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.phase != factionAlly || board.unit("a1").Acted {
		t.Fatal("the board changed on a refusal")
	}
}

func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, factionAlly, 1, armed("a1", factionAlly, 1, 1), armed("a2", factionAlly, 1, 2), armed("e1", factionEnemy, 2, 1))
	dice := battle.Forced{AttackerSupport: true, DefenderSupport: true, Strike: true, Counter: true}

	for acts := 0; len(board.gone()) == 0; acts++ {
		if acts > 100 {
			t.Fatal("no side is gone after 100 activations")
		}
		pending := board.pending(board.phase)
		actor := pending[0]
		targets := board.targetsOf(actor)
		action := standby(actor.ID)
		if len(targets) > 0 {
			action = decision{UnitID: actor.ID, Kind: actionAttack, TargetID: targets[0].ID, Weapon: "gun",
				ResponseAttack: &responseAttack{Stance: stanceNone}}
		}
		if _, err := board.act(action, dice); err != nil {
			t.Fatalf("act %d: %v", acts, err)
		}
	}
}
