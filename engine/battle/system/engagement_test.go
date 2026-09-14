package system

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func hit() *battle.Stated  { return &battle.Stated{Hit: true} }
func miss() *battle.Stated { return &battle.Stated{Hit: false} }

func strikes(events []battle.Event) []battle.StrikeEvent {
	var out []battle.StrikeEvent
	for _, event := range events {
		if s, ok := event.(battle.StrikeEvent); ok {
			out = append(out, s)
		}
	}
	return out
}

func kinds(events []battle.Event) []battle.EventKind {
	out := make([]battle.EventKind, 0, len(events))
	for _, event := range events {
		out = append(out, event.EventKind())
	}
	return out
}

func expectKinds(t *testing.T, events []battle.Event, want ...battle.EventKind) {
	t.Helper()
	if got := kinds(events); !reflect.DeepEqual(got, want) {
		t.Fatalf("events: %v, want %v", got, want)
	}
}

func effectOn(t *testing.T, effects []battle.Effect, unitID int) battle.Effect {
	t.Helper()
	for _, effect := range effects {
		if effect.UnitID == unitID {
			return effect
		}
	}
	t.Fatalf("no effect on unit %d in %+v", unitID, effects)
	return battle.Effect{}
}

func noEffectOn(t *testing.T, effects []battle.Effect, unitID int) {
	t.Helper()
	for _, effect := range effects {
		if effect.UnitID == unitID {
			t.Fatalf("an effect on unit %d: %+v", unitID, effect)
		}
	}
}

func lastActivationEnd(t *testing.T, events []battle.Event) battle.ActivationEndEvent {
	t.Helper()
	for _, event := range events {
		if e, ok := event.(battle.ActivationEndEvent); ok {
			return e
		}
	}
	t.Fatal("no activation end")
	return battle.ActivationEndEvent{}
}

// The shootout holds one unit on each side, so the act of the actor empties
// the ally phase and the rotation walks to the enemy phase.
func TestCommitSettlesAPlainAttack(t *testing.T) {
	b := shootout()
	before := unitOf(b, targetID).Value.HP
	values, events := accepted(t, b, battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit()}, ResponseAttack: none()})

	expectKinds(t, events, battle.EventStrike, battle.EventActivationEnd, battle.EventPhase, battle.EventPhase)
	main := strikes(events)[0]
	if !main.Fired || !main.Landed || main.Critical || main.Damage <= 0 || main.Segment != battle.SegmentMain {
		t.Fatalf("main strike: %+v", main)
	}
	if got := *effectOn(t, main.Effects, targetID).HP; got != (battle.Change[int]{From: before, To: before - main.Damage}) {
		t.Fatalf("hp: %+v", got)
	}
	if got := *effectOn(t, main.Effects, actorID).EN; got != (battle.Change[int]{From: 140, To: 130}) {
		t.Fatalf("en: %+v", got)
	}
	if got := *effectOn(t, lastActivationEnd(t, events).Effects, actorID).Acted; got != (battle.Change[bool]{From: false, To: true}) {
		t.Fatalf("acted: %+v", got)
	}
	if values.Units[targetID].HP != before-main.Damage || values.Phase != battle.FactionEnemy {
		t.Fatalf("values: %+v", values)
	}
	if b.Values.Units[targetID].HP != before {
		t.Fatal("the settlement wrote the column it received")
	}
}

func TestCommitSettlesTheCounterAndBothPay(t *testing.T) {
	_, events := accepted(t, shootout(), battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: miss()},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0), Stated: miss()}})

	got := strikes(events)
	if len(got) != 2 || got[0].Segment != battle.SegmentMain || got[1].Segment != battle.SegmentCounter {
		t.Fatalf("strikes: %+v", got)
	}
	for _, s := range got {
		if !s.Fired || s.Landed || s.Damage != 0 {
			t.Fatalf("a miss: %+v", s)
		}
		noEffectOn(t, s.Effects, s.StruckID)
		if effectOn(t, s.Effects, s.ShooterID).EN == nil {
			t.Fatalf("the shooter did not pay: %+v", s)
		}
	}
}

func TestCommitSettlesAMoveAlone(t *testing.T) {
	step := battle.Cell{1, 0}
	values, events := accepted(t, squad(aside), battle.Action{ActorID: actorID, MoveTo: &step})

	expectKinds(t, events, battle.EventMove, battle.EventActivationEnd)
	if move := events[0].(battle.MoveEvent); move.From != (battle.Cell{0, 0}) || move.To != step {
		t.Fatalf("move: %+v", move)
	}
	if values.Units[actorID].Pos != step || !values.Units[actorID].Acted {
		t.Fatalf("values: %+v", values.Units[actorID])
	}
}

// One support attack of the actor destroys the target. The main strike
// still fires on the wreck and pays, the defender side does not fire, and
// the actor spends one chance step instead of its activation.
func TestCommitSettlesAKillBeforeTheMainStrike(t *testing.T) {
	deadly := func(u []battle.Unit) {
		u[targetID].HP = 1
		u[actorID].ChanceSteps = 1
		u[squadSupporterID].Mech.Weapons[0].Power = 1800
	}
	values, events := accepted(t, squad(deadly), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit(),
			SupportAttackers: []battle.SupportAttacker{{UnitID: squadSupporterID, WeaponID: 0, Stated: hit()}}},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0),
			SupportAttackers: supporters(squadFoeSupporterID)}})

	got := strikes(events)
	if len(got) != 4 {
		t.Fatalf("strikes: %+v", got)
	}
	support, main, foeSupport, counter := got[0], got[1], got[2], got[3]
	if !support.Fired || !support.Landed || effectOn(t, support.Effects, targetID).HP.To != 0 {
		t.Fatalf("support: %+v", support)
	}
	if got := *effectOn(t, support.Effects, squadSupporterID).SupportAttackCharges; got != (battle.Change[int]{From: 1, To: 0}) {
		t.Fatalf("charge: %+v", got)
	}
	if !main.Fired || !main.Landed || main.Damage <= 0 {
		t.Fatalf("main: %+v", main)
	}
	noEffectOn(t, main.Effects, targetID)
	if effectOn(t, main.Effects, actorID).EN == nil {
		t.Fatal("the main strike on a wreck did not pay")
	}
	for _, s := range []battle.StrikeEvent{foeSupport, counter} {
		if s.Fired || s.Reason == "" || len(s.Effects) != 0 {
			t.Fatalf("defender side: %+v", s)
		}
	}
	end := lastActivationEnd(t, events)
	if got := *effectOn(t, end.Effects, actorID).ChanceSteps; got != (battle.Change[int]{From: 1, To: 0}) {
		t.Fatalf("chance steps: %+v", got)
	}
	if values.Units[actorID].Acted || values.Phase != battle.FactionAlly {
		t.Fatalf("values: acted %v phase %s", values.Units[actorID].Acted, values.Phase)
	}
}

// A support defender for the defender takes the support attack and the main
// strike in the defend stance; the first strike that lands spends its one
// charge, the later strike spends none; the target is untouched.
func TestCommitSettlesTheSupportDefenderOfTheDefender(t *testing.T) {
	_, events := accepted(t, squad(nil), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit(),
			SupportAttackers: []battle.SupportAttacker{{UnitID: squadSupporterID, WeaponID: 0, Stated: hit()}}},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone, SupportDefenderID: idOf(squadFoeGuardID)}})

	got := strikes(events)
	for _, s := range got {
		if s.StruckID != squadFoeGuardID || s.AimedID != targetID || !s.Landed {
			t.Fatalf("strike: %+v", s)
		}
		noEffectOn(t, s.Effects, targetID)
		if effectOn(t, s.Effects, squadFoeGuardID).HP == nil {
			t.Fatalf("the support defender took nothing: %+v", s)
		}
	}
	if got := *effectOn(t, got[0].Effects, squadFoeGuardID).SupportDefendCharges; got != (battle.Change[int]{From: 1, To: 0}) {
		t.Fatalf("charge on the first strike: %+v", got)
	}
	if effectOn(t, got[1].Effects, squadFoeGuardID).SupportDefendCharges != nil {
		t.Fatalf("charge on the second strike: %+v", got[1])
	}
}

func TestCommitSettlesAMissOnTheSupportDefenderWithNoCharge(t *testing.T) {
	_, events := accepted(t, squad(nil), battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: miss()},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone, SupportDefenderID: idOf(squadFoeGuardID)}})

	noEffectOn(t, strikes(events)[0].Effects, squadFoeGuardID)
}

func TestCommitSettlesTheSupportDefenderOfTheActor(t *testing.T) {
	_, events := accepted(t, squad(nil), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: miss(), SupportDefenderID: idOf(squadGuardID)},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0), Stated: hit(),
			SupportAttackers: []battle.SupportAttacker{{UnitID: squadFoeSupporterID, WeaponID: 0, Stated: hit()}}}})

	got := strikes(events)
	for _, s := range got[1:] {
		if s.StruckID != squadGuardID || s.AimedID != actorID || effectOn(t, s.Effects, squadGuardID).HP == nil {
			t.Fatalf("the strike of the defender side lands on the support defender of the actor: %+v", s)
		}
		noEffectOn(t, s.Effects, actorID)
	}
	if got := *effectOn(t, got[1].Effects, squadGuardID).SupportDefendCharges; got != (battle.Change[int]{From: 1, To: 0}) {
		t.Fatalf("charge on the support attack: %+v", got)
	}
	if effectOn(t, got[2].Effects, squadGuardID).SupportDefendCharges != nil {
		t.Fatalf("charge on the counter: %+v", got[2])
	}
}

func TestCommitSettlesADebuffAndKeepsTheLargerMagnitude(t *testing.T) {
	kind := "attack"
	debuffing := func(u []battle.Unit) {
		u[actorID].Mech.Weapons[0].DebuffKind, u[actorID].Mech.Weapons[0].DebuffMagnitude = &kind, 0.1
		u[squadSupporterID].Mech.Weapons[0].DebuffKind, u[squadSupporterID].Mech.Weapons[0].DebuffMagnitude = &kind, 0.3
	}
	values, events := accepted(t, squad(debuffing), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit(),
			SupportAttackers: []battle.SupportAttacker{{UnitID: squadSupporterID, WeaponID: 0, Stated: hit()}}},
		ResponseAttack: none()})

	want := []battle.Debuff{{Kind: kind, Magnitude: 0.3, AppliedPhase: 3}}
	if got := values.Units[targetID].Debuffs; !reflect.DeepEqual(got, want) {
		t.Fatalf("debuffs: %+v", got)
	}
	if got := effectOn(t, strikes(events)[1].Effects, targetID).Debuffs; !reflect.DeepEqual(got.From, want) || !reflect.DeepEqual(got.To, want) {
		t.Fatalf("debuff change on the main strike: %+v", got)
	}
}

func TestCommitDrawsTheBehaviorsOfAStrikeWithNoStatement(t *testing.T) {
	sure := beamOf(200)
	certain := func(u []battle.Unit) { u[actorID].Mech.Weapons = []battle.Weapon{sure} }
	_, events := accepted(t, squad(certain), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID}, ResponseAttack: none()})

	if main := strikes(events)[0]; !main.Landed || main.Critical {
		t.Fatalf("a draw at hit rate 1: %+v", main)
	}
}

func TestCommitRotatesThePhaseWhenTheLastUnitActs(t *testing.T) {
	values, events := accepted(t, shootout(), battle.Action{ActorID: actorID})

	expectKinds(t, events, battle.EventActivationEnd, battle.EventPhase, battle.EventPhase)
	last := events[2].(battle.PhaseEvent)
	if last.Phase != battle.FactionEnemy || last.Turn != 1 || values.Phase != battle.FactionEnemy {
		t.Fatalf("rotation: %+v values %+v", last, values)
	}
}
