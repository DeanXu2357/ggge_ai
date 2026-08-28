package battle

import (
	"reflect"
	"testing"
)

func turnBoard(t *testing.T, phase Faction, turn int, units ...Unit) *Board {
	t.Helper()
	board, err := NewBoard(Bounds{High: Cell{5, 4}}, units)
	if err != nil {
		t.Fatal(err)
	}
	board.Phase = phase
	board.Turn = turn
	return board
}

func basicUnit(id string, faction Faction, x, y int) Unit {
	return Unit{
		ID: id, Faction: faction, Footprint: Footprint{Anchor: Cell{x, y}, Size: Size{1, 1}},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140, Mech: Mech{MoveRange: 1},
	}
}

func armed(id string, faction Faction, x, y int) Unit {
	out := basicUnit(id, faction, x, y)
	out.Mech.Weapons = []Weapon{{Name: "gun", Power: 5000, Range: RadiusRange{1, 3}, Accuracy: 100, CanCounter: true, UsableAfterMove: true}}
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func standby(id string) Decision {
	return Decision{UnitID: id, Kind: ActionStandby}
}

func TestPendingHoldsTheLivingUnitsOfTheSideThatDidNotAct(t *testing.T) {
	acted := basicUnit("a2", FactionAlly, 1, 2)
	acted.Acted = true
	dead := basicUnit("a3", FactionAlly, 1, 3)
	dead.HP = 0
	board := turnBoard(t, FactionAlly, 1, basicUnit("a1", FactionAlly, 1, 1), acted, dead, basicUnit("e1", FactionEnemy, 4, 4))

	var ids []string
	for _, pending := range board.Pending(FactionAlly) {
		ids = append(ids, pending.ID)
	}
	if !reflect.DeepEqual(ids, []string{"a1"}) {
		t.Fatalf("pending: %v", ids)
	}
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, basicUnit("a1", FactionAlly, 1, 1), basicUnit("a2", FactionAlly, 1, 2), basicUnit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("a1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(resolution.Rotations) != 0 || board.Phase != FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", resolution.Rotations, board.Turn, board.Phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, basicUnit("a1", FactionAlly, 1, 1), basicUnit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("a1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []Rotation{{Turn: 1, Phase: FactionThirdParty}, {Turn: 1, Phase: FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.Phase != FactionEnemy || board.Turn != 1 {
		t.Fatalf("turn %d phase %s", board.Turn, board.Phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := basicUnit("a1", FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	board := turnBoard(t, FactionEnemy, 1, ally, basicUnit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("e1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(resolution.Rotations, []Rotation{{Turn: 2, Phase: FactionAlly}}) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	got := board.Unit("a1")
	if got.Acted || got.EN != 140 {
		t.Fatalf("the phase start must reset the activation and cap the regeneration: %+v", got)
	}
	if enemy := board.Unit("e1"); !enemy.Acted || enemy.EN != 100 {
		t.Fatalf("the enemy side must keep its state until its own phase start: %+v", enemy)
	}
}

func TestThePhaseStartRegeneratesTenPercentOfTheMaximumFloored(t *testing.T) {
	ally := basicUnit("a1", FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	board := turnBoard(t, FactionEnemy, 1, ally, basicUnit("e1", FactionEnemy, 4, 4))

	if _, err := board.Act(standby("e1"), NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.Unit("a1").EN; got != 61 {
		t.Fatalf("EN: %d, want 10 + floor(51.3)", got)
	}
}

func TestADebuffExpiresWhenItsRoundEnds(t *testing.T) {
	ally := basicUnit("a1", FactionAlly, 1, 1)
	ally.Acted = true
	ally.Debuffs = []Debuff{
		{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3},
		{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4},
	}
	enemy := basicUnit("e1", FactionEnemy, 4, 4)
	enemy.Debuffs = []Debuff{{Kind: "defense", Magnitude: 0.3, AppliedPhase: 3}}
	board := turnBoard(t, FactionEnemy, 1, ally, enemy)

	if _, err := board.Act(standby("e1"), NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.Unit("a1").Debuffs; !reflect.DeepEqual(got, []Debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := board.Unit("e1").Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	board := turnBoard(t, FactionEnemy, 2, basicUnit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("e1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []Rotation{{Turn: 3, Phase: FactionAlly}, {Turn: 3, Phase: FactionThirdParty}, {Turn: 3, Phase: FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.Unit("e1").Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}

func TestGoneNamesTheSidesWithNoLivingUnit(t *testing.T) {
	dead := basicUnit("e1", FactionEnemy, 4, 4)
	dead.HP = 0
	board := turnBoard(t, FactionAlly, 1, basicUnit("a1", FactionAlly, 1, 1), dead)

	if got := board.Gone(); !reflect.DeepEqual(got, []Faction{FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
	board.Unit("a1").HP = 0
	if got := board.Gone(); !reflect.DeepEqual(got, []Faction{FactionAlly, FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := basicUnit("a1", FactionAlly, 1, 1)
	board := turnBoard(t, FactionAlly, 1, last)
	board.Unit("a1").HP = 0

	if got := board.Advance(); len(got) != 0 || board.Phase != FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, basicUnit("a1", FactionAlly, 1, 1), basicUnit("e1", FactionEnemy, 4, 4))

	if _, err := board.Act(standby("e1"), NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.Phase != FactionAlly || board.Unit("a1").Acted {
		t.Fatal("the board changed on a refusal")
	}
}

func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, armed("a1", FactionAlly, 1, 1), armed("a2", FactionAlly, 1, 2), armed("e1", FactionEnemy, 2, 1))
	dice := Forced{AttackerSupport: true, DefenderSupport: true, Strike: true, Counter: true}

	for acts := 0; len(board.Gone()) == 0; acts++ {
		if acts > 100 {
			t.Fatal("no side is gone after 100 activations")
		}
		pending := board.Pending(board.Phase)
		actor := pending[0]
		targets := board.TargetsOf(actor)
		decision := standby(actor.ID)
		if len(targets) > 0 {
			decision = Decision{UnitID: actor.ID, Kind: ActionAttack, TargetID: targets[0].ID, Weapon: "gun",
				ResponseAttack: &ResponseAttack{Stance: StanceNone}}
		}
		if _, err := board.Act(decision, dice); err != nil {
			t.Fatalf("act %d: %v", acts, err)
		}
	}
}
