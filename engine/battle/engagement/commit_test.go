package engagement

import (
	"errors"
	"fmt"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func shootout() *state.Board {
	attacker := fighter("a1", state.FactionAlly, state.Cell{0, 0})
	attacker.Mech.Weapons = []def.Weapon{beam()}
	target := fighter("e1", state.FactionEnemy, state.Cell{3, 0})
	target.Mech.Weapons = []def.Weapon{beam()}
	return board(attacker, target)
}

func covered() *state.Board {
	b := shootout()
	supporter := fighter("a2", state.FactionAlly, state.Cell{1, 1})
	supporter.Mech.Weapons = []def.Weapon{beam()}
	supporter.Mech.MoveRange = 2
	supporter.SupportAttackCharges = 1
	guard := fighter("e2", state.FactionEnemy, state.Cell{2, 0})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	b.Units = append(b.Units, supporter, guard)
	return b
}

func attackOn(target string, weapon string) Decision {
	return Decision{UnitID: "a1", Kind: ActionAttack, TargetID: target, Weapon: weapon}
}

func resolve(b *state.Board, decision Decision, dice battle.Dice) (Trace, error) {
	plan, err := Prepare(b, decision)
	if err != nil {
		return nil, err
	}
	return Commit(b, plan, dice), nil
}

func apply(t *testing.T, b *state.Board, decision Decision, dice battle.Dice) Trace {
	t.Helper()
	trace, err := resolve(b, decision, dice)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	return trace
}

func TestTheMoveComesBeforeTheStrike(t *testing.T) {
	b := shootout()
	b.Unit("a1").Mech.MoveRange = 2
	b.Unit("e1").Footprint.Anchor = state.Cell{4, 0}
	anchor := state.Cell{1, 0}

	trace := apply(t, b, Decision{UnitID: "a1", Kind: ActionAttack, MoveTo: &anchor,
		TargetID: "e1", Weapon: "beam rifle"}, battle.Forced{Strike: true})

	if got := b.Unit("a1").Footprint.Anchor; got != anchor {
		t.Fatalf("anchor: %v", got)
	}
	if len(trace) != 1 || trace[0].Kind != StrikeMain || !trace[0].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if b.Unit("e1").HP >= 12000 || b.Unit("a1").EN != 130 {
		t.Fatalf("the strike takes hit points and energy: %+v", b.Units)
	}
	if !b.Unit("a1").Acted {
		t.Fatal("an attack ends the activation")
	}
}

func TestAnIllegalMoveStopsTheAction(t *testing.T) {
	far := state.Cell{4, 4}
	near := state.Cell{1, 0}
	cases := map[string]struct {
		build    func(*state.Board)
		decision Decision
	}{
		"an anchor out of the move range": {
			func(b *state.Board) { b.Unit("a1").Mech.MoveRange = 1 },
			Decision{UnitID: "a1", Kind: ActionAttack, MoveTo: &far,
				TargetID: "e1", Weapon: "beam rifle"},
		},
		"a weapon that fires before the move": {
			func(b *state.Board) {
				b.Unit("a1").Mech.MoveRange = 2
				b.Unit("a1").Mech.Weapons[0].UsableAfterMove = false
			},
			Decision{UnitID: "a1", Kind: ActionAttack, MoveTo: &near,
				TargetID: "e1", Weapon: "beam rifle"},
		},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			b := shootout()
			one.build(b)

			_, err := resolve(b, one.decision, battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalMove) {
				t.Fatalf("error: %v", err)
			}
			if b.Unit("a1").Footprint.Anchor != (state.Cell{0, 0}) || b.Unit("a1").Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestADestroyedUnitKeepsItsPlaceWithNoHitPointsLeft(t *testing.T) {
	b := shootout()
	b.Unit("e1").HP = 1

	trace := apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if got := b.Unit("e1"); got == nil || got.HP != 0 || alive(got) {
		t.Fatalf("unit: %+v", got)
	}
	if !trace[0].Killed {
		t.Fatalf("trace: %+v", trace)
	}
	if len(byFaction(b, state.FactionEnemy)) != 0 || len(b.Units) != 2 {
		t.Fatal("a roster query filters on Alive, and the board keeps the unit")
	}
}

func TestAKillGivesTheAttackerItsActivationAgain(t *testing.T) {
	b := shootout()
	b.Unit("e1").HP = 1
	b.Unit("a1").ChanceSteps = 1
	b.Unit("a1").ChanceStepsMax = 1

	apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if b.Unit("a1").Acted || b.Unit("a1").ChanceSteps != 0 {
		t.Fatalf("actor: %+v", b.Unit("a1"))
	}
}

func TestAKillWithNoChanceStepLeftEndsTheActivation(t *testing.T) {
	b := shootout()
	b.Unit("e1").HP = 1

	apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if !b.Unit("a1").Acted {
		t.Fatal("the unit holds no chance step, so the kill gives no second activation")
	}
}

func TestTheSupportDefenderTakesEveryShotAndOneCharge(t *testing.T) {
	b := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2"}
	decision.Response = &Response{Stance: StanceDodge, SupportDefender: "e2"}

	trace := apply(t, b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 2 || trace[0].StruckID != "e2" || trace[1].StruckID != "e2" {
		t.Fatalf("every shot goes to the support defender: %+v", trace)
	}
	if b.Unit("e2").SupportDefendCharges != 0 {
		t.Fatal("every shot together spends one charge")
	}
	if b.Unit("e1").HP != 12000 {
		t.Fatal("the target takes nothing")
	}
	if b.Unit("a2").SupportAttackCharges != 0 || b.Unit("a2").EN != 130 {
		t.Fatalf("the supporter spends one charge and the energy of its weapon: %+v",
			b.Unit("a2"))
	}
}

func TestASupportAttackThatMissesSpendsNoSupportDefendCharge(t *testing.T) {
	b := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2"}
	decision.Response = &Response{Stance: StanceDodge, SupportDefender: "e2"}

	apply(t, b, decision, battle.Forced{})

	if b.Unit("e2").SupportDefendCharges != 1 || b.Unit("e2").HP != 12000 {
		t.Fatalf("supportDefender: %+v", b.Unit("e2"))
	}
	if b.Unit("a2").SupportAttackCharges != 0 || b.Unit("a2").EN != 130 {
		t.Fatal("a supporter that misses spends its charge and its energy")
	}
}

func TestTheSupportAttackOfTheAttackerIsAChoice(t *testing.T) {
	b := covered()

	trace := apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 1 || trace[0].Kind != StrikeMain {
		t.Fatalf("the action names no support attacker, so none fires: %+v", trace)
	}
	if b.Unit("a2").SupportAttackCharges != 1 {
		t.Fatal("the supporter keeps its charge")
	}
}

func TestTheRulesCapTheNumberOfSupportAttackers(t *testing.T) {
	b := covered()
	names := []string{"a2"}
	for index := 0; index <= maxSupportAttackers; index++ {
		joining := fighter(fmt.Sprintf("a%d", index+3), state.FactionAlly, state.Cell{2, index + 1})
		joining.Mech.Weapons = []def.Weapon{beam()}
		joining.Mech.MoveRange = 3
		joining.SupportAttackCharges = 1
		b.Units = append(b.Units, joining)
		names = append(names, joining.ID)
	}
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = names

	_, err := resolve(b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the cap of the rules is %d units: %v", maxSupportAttackers, err)
	}
	for _, name := range names {
		if b.Unit(name).SupportAttackCharges != 1 {
			t.Fatalf("an error leaves the board as it was: %q", name)
		}
	}
}

func TestTheDefenderRepliesWithItsSupportAndItsCounter(t *testing.T) {
	b := covered()
	b.Unit("e2").SupportAttackCharges = 1
	b.Unit("e2").Mech.Weapons = []def.Weapon{beam()}
	decision := attackOn("e1", "beam rifle")
	decision.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle",
		SupportAttackers: []string{"e2"}}

	trace := apply(t, b, decision, battle.Forced{DefenderSupport: true, Strike: true, Counter: true})

	kinds := []StrikeKind{trace[0].Kind, trace[1].Kind, trace[2].Kind}
	want := []StrikeKind{StrikeMain, StrikeDefenderSupport, StrikeCounter}
	if len(trace) != 3 || kinds[0] != want[0] || kinds[1] != want[1] || kinds[2] != want[2] {
		t.Fatalf("the support attack of the defender comes before its counter: %+v", trace)
	}
	if !trace[1].Landed {
		t.Fatal("the support attack of the defender reads the node of its own side")
	}
	if b.Unit("a1").HP >= 12000 || b.Unit("e1").EN != 130 {
		t.Fatalf("attacker: %+v", b.Unit("a1"))
	}
}

func TestACounterThatMissesSpendsItsEnergy(t *testing.T) {
	b := shootout()
	decision := attackOn("e1", "beam rifle")
	decision.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle"}

	trace := apply(t, b, decision, battle.Forced{Strike: true})

	if len(trace) != 2 || trace[1].Kind != StrikeCounter || trace[1].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if b.Unit("e1").EN != 130 || b.Unit("a1").HP != 12000 {
		t.Fatalf("the weapon spends its energy on a miss: %+v", b.Unit("e1"))
	}
}

func TestADeadTargetRepliesWithNothing(t *testing.T) {
	b := shootout()
	b.Unit("e1").HP = 1
	decision := attackOn("e1", "beam rifle")
	decision.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle"}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	if len(trace) != 1 || b.Unit("a1").HP != 12000 {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheSupportDefendWhenAttackTakesTheCounterForTheAttacker(t *testing.T) {
	b := shootout()
	bearer := fighter("a2", state.FactionAlly, state.Cell{0, 1})
	bearer.Mech.MoveRange = 1
	bearer.SupportDefendWhenAttack = true
	bearer.SupportDefendCharges = 1
	b.Units = append(b.Units, bearer)
	decision := attackOn("e1", "beam rifle")
	decision.SupportDefender = "a2"
	decision.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle"}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	if trace[1].StruckID != "a2" || b.Unit("a1").HP != 12000 {
		t.Fatalf("the bearer takes the counter: %+v", trace)
	}
	if b.Unit("a2").SupportDefendCharges != 0 || b.Unit("a2").HP >= 12000 {
		t.Fatalf("bearer: %+v", b.Unit("a2"))
	}
}

func TestADebuffReplacesAWeakerOneAndLeavesAStrongerOne(t *testing.T) {
	net := beam()
	net.Name, net.DebuffKind, net.DebuffMagnitude = "wire net", "armor_break", 0.2
	cases := map[string]struct {
		start float64
		want  float64
	}{"weaker": {0.1, 0.2}, "stronger": {0.5, 0.5}}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			b := shootout()
			b.Unit("a1").Mech.Weapons = []def.Weapon{net}
			b.Unit("e1").Debuffs = []state.Debuff{
				{Kind: "mobility_down", Magnitude: 0.3, AppliedPhase: 1},
				{Kind: "armor_break", Magnitude: one.start, AppliedPhase: 1},
			}

			apply(t, b, attackOn("e1", "wire net"), battle.Forced{Strike: true})

			debuffs := b.Unit("e1").Debuffs
			if len(debuffs) != 2 {
				t.Fatalf("debuffs: %+v", debuffs)
			}
			last := debuffs[len(debuffs)-1]
			if last.Kind != "armor_break" || last.Magnitude != one.want {
				t.Fatalf("debuffs: %+v", debuffs)
			}
			if one.start != one.want && last.AppliedPhase != turn.PhaseIndex(b) {
				t.Fatalf("a fresh debuff carries the phase of this strike: %+v", last)
			}
		})
	}
}

func TestAMapAttackIsRefusedAndLeavesTheBoard(t *testing.T) {
	b := shootout()
	shells := beam()
	shells.Name, shells.MapWeapon, shells.ENCost = "shells", true, 5
	b.Unit("a1").Mech.Weapons = []def.Weapon{shells}
	b.Unit("a1").Ammo = map[string]int{"shells": 2}
	aim := state.Cell{3, 0}

	_, err := resolve(b, Decision{UnitID: "a1", Kind: ActionMapAttack,
		Weapon: "shells", Aim: &aim}, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the engine resolves no map attack: %v", err)
	}
	if b.Unit("e1").HP != 12000 || b.Unit("a1").Ammo["shells"] != 2 ||
		b.Unit("a1").Acted {
		t.Fatalf("the refused action changes no field: %+v", b.Unit("a1"))
	}
}

func TestASkillIsRefusedAndLeavesTheBoard(t *testing.T) {
	b := shootout()
	b.Unit("a1").HP = 8000
	b.Unit("a1").Skills = []state.Skill{{Kind: "skill_heal", Uses: 1}}

	_, err := resolve(b, Decision{UnitID: "a1", Kind: "skill_heal"}, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the engine resolves no skill: %v", err)
	}
	if b.Unit("a1").HP != 8000 || b.Unit("a1").Skills[0].Uses != 1 ||
		b.Unit("a1").Acted {
		t.Fatalf("the refused action changes no field: %+v", b.Unit("a1"))
	}
}

type probes map[battle.Node]float64

func (p probes) Lands(node battle.Node, probability float64) bool {
	p[node] = probability
	return true
}

func TestAStrikeNamesALivingFoeAndNoOtherUnit(t *testing.T) {
	cases := map[string]string{"an ally": "a2", "the actor itself": "a1"}

	for name, target := range cases {
		t.Run(name, func(t *testing.T) {
			b := shootout()
			b.Units = append(b.Units, fighter("a2", state.FactionAlly, state.Cell{1, 0}))

			_, err := resolve(b, attackOn(target, "beam rifle"), battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Unit(target).HP != 12000 {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAResponseAttackThatBreaksARuleIsAnError(t *testing.T) {
	cases := map[string]Response{
		"a defense that takes a support defender as well": {Stance: StanceDefend,
			SupportDefender: "e2"},
		"a unit of the other side as the support defender": {Stance: StanceDodge,
			SupportDefender: "a2"},
		"a support attacker that reaches nothing": {Stance: StanceDodge,
			SupportAttackers: []string{"e2"}},
		"a weapon on a stance that fires none": {Stance: StanceDodge, Weapon: "beam rifle"},
		"a counter with a weapon the unit does not carry": {Stance: StanceCounter,
			Weapon: "wire net"},
	}

	for name, response := range cases {
		t.Run(name, func(t *testing.T) {
			b := covered()
			decision := attackOn("e1", "beam rifle")
			decision.Response = &response

			_, err := resolve(b, decision, battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Unit("e1").HP != 12000 || b.Unit("a1").Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAStrikeWithNoResponseAttackAndOneWithACounterBothRun(t *testing.T) {
	b := shootout()
	counter := attackOn("e1", "beam rifle")
	counter.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle"}

	apply(t, b, counter, battle.Forced{Strike: true, Counter: true})

	b = shootout()
	apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if b.Unit("e1").HP >= 12000 {
		t.Fatal("a strike that carries no response attack stays legal")
	}
}

func TestTheHitRateOfTheStrikeReadsTheTargetAndNotTheCover(t *testing.T) {
	b := covered()
	b.Unit("e2").Mech.Mobility = 900
	b.Unit("e2").Pilot.Reaction = 900
	decision := attackOn("e1", "beam rifle")
	decision.Response = &Response{Stance: StanceDodge, SupportDefender: "e2"}
	nodes := probes{}

	trace, err := resolve(b, decision, nodes)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}

	weapon := beam()
	want := strikeHitProbability(b.Unit("a1"), b.Unit("e1"), &weapon, true)
	if trace[0].StruckID != "e2" {
		t.Fatalf("the support defender takes the strike: %+v", trace)
	}
	if nodes[battle.NodeStrike] != want {
		t.Fatalf("hit rate: %v, and the target gives %v", nodes[battle.NodeStrike], want)
	}
}

func TestAnActionOutsideTheBoardIsAnError(t *testing.T) {
	cases := map[string]Decision{
		"an unknown unit":   {UnitID: "ghost", Kind: ActionStandby},
		"an unknown target": attackOn("ghost", "beam rifle"),
		"an unknown weapon": attackOn("e1", "lance"),
		"a map weapon on an attack": {UnitID: "a1", Kind: ActionAttack,
			TargetID: "e1", Weapon: "shells"},
		"a weapon out of its band": {UnitID: "a1", Kind: ActionAttack,
			TargetID: "e2", Weapon: "beam rifle"},
	}

	for name, decision := range cases {
		t.Run(name, func(t *testing.T) {
			b := shootout()
			shells := beam()
			shells.Name, shells.MapWeapon = "shells", true
			b.Unit("a1").Mech.Weapons = append(b.Unit("a1").Mech.Weapons, shells)
			b.Units = append(b.Units, fighter("e2", state.FactionEnemy, state.Cell{4, 4}))

			if _, err := resolve(b, decision, battle.Forced{Strike: true}); err == nil {
				t.Fatal("the action stands outside the board")
			}
		})
	}
}

func TestAnUnpaidWeaponAndAnEmptyCounterAreErrors(t *testing.T) {
	b := shootout()
	b.Unit("a1").EN = 9
	if _, err := resolve(b, attackOn("e1", "beam rifle"), battle.Forced{}); !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}

	b = shootout()
	b.Unit("e1").Mech.Weapons[0].CanCounter = false
	decision := attackOn("e1", "beam rifle")
	decision.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle"}

	_, err := resolve(b, decision, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if b.Unit("e1").HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestAUnitThatCannotActRunsNoAction(t *testing.T) {
	b := shootout()
	b.Unit("a1").Acted = true

	_, err := resolve(b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrActed) {
		t.Fatalf("error: %v", err)
	}
}

func TestAStandbyEndsTheActivationAndAsksNoDie(t *testing.T) {
	b := shootout()

	trace := apply(t, b, Decision{UnitID: "a1", Kind: ActionStandby}, battle.Forced{})

	if len(trace) != 0 || !b.Unit("a1").Acted {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheAttackerNamesAUnitThatCanTakeTheCounterForIt(t *testing.T) {
	b := shootout()
	plain := fighter("a2", state.FactionAlly, state.Cell{0, 1})
	plain.Mech.MoveRange = 1
	plain.SupportDefendCharges = 1
	b.Units = append(b.Units, plain)
	decision := attackOn("e1", "beam rifle")
	decision.SupportDefender = "a2"
	decision.Response = &Response{Stance: StanceCounter, Weapon: "beam rifle"}

	_, err := resolve(b, decision, battle.Forced{Strike: true, Counter: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("a unit with no attack shield takes no counter for its side: %v", err)
	}
	if b.Unit("a1").Acted || b.Unit("e1").HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestASupportAttackerJoinsOneStrikeOneTime(t *testing.T) {
	b := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2", "a2"}

	_, err := resolve(b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if b.Unit("a2").SupportAttackCharges != 1 {
		t.Fatal("an error leaves the board as it was")
	}
}
