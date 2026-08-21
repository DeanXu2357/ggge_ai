package battle

import (
	"bytes"
	"encoding/json"
	"reflect"
	"testing"
)

// spent gives a board on which the ally side is done and the enemy side waits.
func spent() *Board {
	ally := fighter("a1", FactionAlly, Cell{0, 0})
	ally.Weapons = []Weapon{beam()}
	ally.Acted = true
	ally.EN = 100
	ally.ChanceStepsMax, ally.SupportAttackChargesMax = 1, 2
	foe := fighter("e1", FactionEnemy, Cell{3, 0})
	foe.Weapons = []Weapon{beam()}
	return board(ally, foe)
}

func TestThePendingUnitsHoldTheLivingUnitsOfTheSideThatWait(t *testing.T) {
	state := spent()
	state.Units = append(state.Units, fighter("e2", FactionEnemy, Cell{4, 0}))
	state.Unit("e2").HP = 0

	if got := ids(state.PendingUnits(FactionAlly)); len(got) != 0 {
		t.Fatalf("the ally side acted: %v", got)
	}
	if got := ids(state.PendingUnits(FactionEnemy)); !reflect.DeepEqual(got, []string{"e1"}) {
		t.Fatalf("pending: %v", got)
	}
}

func TestThePhaseStartGivesTheActivationTheChargesAndTheEnergyBack(t *testing.T) {
	state := spent()
	ally := state.Unit("a1")
	ally.ChanceSteps, ally.SupportAttackCharges = 0, 0

	state.BeginPhase(FactionAlly)

	if ally.Acted || ally.ChanceSteps != 1 || ally.SupportAttackCharges != 2 {
		t.Fatalf("refresh: %+v", *ally)
	}
	if ally.EN != 114 {
		t.Fatalf("the regeneration of a tenth of 140 gives 14: %d", ally.EN)
	}
}

func TestTheEnergyRegenerationStopsAtTheMaximum(t *testing.T) {
	state := spent()
	ally := state.Unit("a1")
	ally.EN = ally.ENMax

	state.BeginPhase(FactionAlly)

	if ally.EN != ally.ENMax {
		t.Fatalf("energy: %d", ally.EN)
	}
}

func TestThePhaseStartLeavesTheOtherSideAlone(t *testing.T) {
	state := spent()
	foe := state.Unit("e1")
	foe.EN, foe.Acted = 20, true

	state.BeginPhase(FactionAlly)

	if foe.EN != 20 || !foe.Acted {
		t.Fatalf("the enemy side moved: %+v", *foe)
	}
}

func TestTheRotationRunsTheOrderOfThePhases(t *testing.T) {
	state := spent()
	state.Unit("e1").Acted = true

	rotations := state.AdvanceUntilPending()

	want := []Faction{FactionThirdParty, FactionEnemy}
	got := make([]Faction, 0, len(rotations))
	for _, rotation := range rotations {
		got = append(got, rotation.Phase)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("rotations: %v", got)
	}
	if state.Turn != 1 {
		t.Fatalf("the turn opens again at the ally side: %d", state.Turn)
	}
}

func TestARotationBackToTheAllySideOpensTheNextTurn(t *testing.T) {
	state := spent()
	state.Phase = FactionEnemy
	state.Unit("e1").Acted = true

	state.AdvanceUntilPending()

	if state.Turn != 2 || state.Phase != FactionAlly {
		t.Fatalf("turn %d, phase %s", state.Turn, state.Phase)
	}
	if state.Unit("a1").Acted {
		t.Fatalf("the new phase gives the activation back")
	}
}

func TestTheGuardStopsARotationThatNoSideCanEnd(t *testing.T) {
	state := spent()
	state.Unit("e1").Acted = true
	state.Unit("a1").HP = 0
	state.Unit("e1").HP = 0

	rotations := state.AdvanceUntilPending()

	if len(rotations) != len(PhaseOrder)+1 {
		t.Fatalf("rotations: %d", len(rotations))
	}
}

func TestADebuffLivesForOneRoundOfThePhaseOrder(t *testing.T) {
	state := spent()
	foe := state.Unit("e1")
	foe.Debuffs = []Debuff{{Kind: "armor_break", Magnitude: 0.2, AppliedPhase: state.PhaseIndex()}}

	state.AdvanceUntilPending()
	if len(foe.Debuffs) != 1 {
		t.Fatalf("the debuff of this phase lives on the next one: %+v", foe.Debuffs)
	}
	foe.Acted = true
	state.AdvanceUntilPending()
	state.Unit("a1").Acted = true
	state.AdvanceUntilPending()

	if len(state.Unit("e1").Debuffs) != 0 {
		t.Fatalf("debuffs: %+v", state.Unit("e1").Debuffs)
	}
}

func TestTheActivationRunsTheTurnCycleAfterTheStrike(t *testing.T) {
	state := spent()
	state.Phase = FactionEnemy

	resolution, err := state.Act(strikeOf("e1", "a1", "beam rifle"), Forced{Strike: true})
	if err != nil {
		t.Fatalf("act: %v", err)
	}

	if len(resolution.Trace) != 1 || !resolution.Trace[0].Landed {
		t.Fatalf("trace: %+v", resolution.Trace)
	}
	if len(resolution.Rotations) != 1 || state.Phase != FactionAlly || state.Turn != 2 {
		t.Fatalf("turn %d, phase %s, rotations %+v", state.Turn, state.Phase, resolution.Rotations)
	}
}

func TestAnActivationThatLeavesAUnitWaitingKeepsThePhase(t *testing.T) {
	state := spent()
	state.Units = append(state.Units, fighter("e2", FactionEnemy, Cell{4, 0}))
	state.Phase = FactionEnemy

	resolution, err := state.Act(Decision{UnitID: "e1", Kind: ActionStandby}, Forced{})
	if err != nil {
		t.Fatalf("act: %v", err)
	}

	if len(resolution.Rotations) != 0 || state.Phase != FactionEnemy {
		t.Fatalf("phase %s, rotations %+v", state.Phase, resolution.Rotations)
	}
}

func TestAFailedActivationLeavesTheBoardAsItWas(t *testing.T) {
	state := spent()
	state.Phase = FactionEnemy
	before := state.Unit("a1").HP

	_, err := state.Act(strikeOf("e1", "a1", "no such weapon"), Forced{Strike: true})

	if err == nil {
		t.Fatal("a weapon that the unit does not carry is no action")
	}
	if state.Unit("a1").HP != before || state.Unit("e1").Acted {
		t.Fatalf("the board moved: %+v", *state.Unit("e1"))
	}
}

func TestACloneRunsTheActivationOnItsOwnUnits(t *testing.T) {
	state := spent()
	state.Phase = FactionEnemy
	state.Unit("e1").Ammo = map[string]int{"beam rifle": 2}
	before := state.Unit("a1").HP

	next := state.Clone()
	if _, err := next.Act(strikeOf("e1", "a1", "beam rifle"), Forced{Strike: true}); err != nil {
		t.Fatalf("act: %v", err)
	}

	if state.Unit("a1").HP != before {
		t.Fatalf("the strike reached the board of before: %d", state.Unit("a1").HP)
	}
	if next.Unit("a1").HP >= before {
		t.Fatalf("the strike reached no unit of the clone: %d", next.Unit("a1").HP)
	}
	next.Unit("e1").Ammo["beam rifle"] = 0
	if state.Unit("e1").Ammo["beam rifle"] != 2 {
		t.Fatalf("the two boards share the ammunition")
	}
}

func strikeOf(actor, target, weapon string) Decision {
	return Decision{UnitID: actor, Kind: ActionAttack, TargetID: target, Weapon: weapon}
}

// A clone shares nothing that one activation writes, so the board of before
// comes out byte for byte after the run.
func TestACloneWritesNothingIntoTheBoardOfBefore(t *testing.T) {
	state := scripted(EventTable{"wave_2": {
		ID:      "wave_2",
		Trigger: Trigger{Kind: TriggerKill, UnitID: "a1"},
		Effect:  Effect{Kind: EffectSpawn, Units: []Unit{fighter("e9", FactionEnemy, Cell{4, 0})}},
	}})
	state.Phase = FactionEnemy
	state.Unit("e1").Ammo = map[string]int{"beam rifle": 1}
	state.Unit("e1").Skills = []Skill{{Kind: ActionSkillHeal, Uses: 1, EndsActivation: true}}
	state.Unit("a1").HP = 1
	state.Unit("a1").Debuffs = []Debuff{{Kind: "armor_break", Magnitude: 0.2}}
	before, err := json.Marshal(EncodeState(state))
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	next := state.Clone()
	if _, err := next.Act(strikeOf("e1", "a1", "beam rifle"), Forced{Strike: true}); err != nil {
		t.Fatalf("act: %v", err)
	}
	if next.Unit("e9") == nil || len(next.FiredEvents) != 1 {
		t.Fatalf("the kill fired no event: %v", next.FiredEvents)
	}

	after, err := json.Marshal(EncodeState(state))
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !bytes.Equal(before, after) {
		t.Fatalf("the board of before moved:\n%s\n%s", before, after)
	}
}
