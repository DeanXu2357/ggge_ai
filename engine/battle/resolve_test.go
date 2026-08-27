package battle

import (
	"errors"
	"fmt"
	"testing"
)

func shootout() *Board {
	attacker := fighter("a1", FactionAlly, Cell{0, 0})
	attacker.Weapons = []Weapon{beam()}
	target := fighter("e1", FactionEnemy, Cell{3, 0})
	target.Weapons = []Weapon{beam()}
	return board(attacker, target)
}

func covered() *Board {
	state := shootout()
	supporter := fighter("a2", FactionAlly, Cell{1, 1})
	supporter.Weapons = []Weapon{beam()}
	supporter.MoveRange = 2
	supporter.SupportAttackCharges = 1
	guard := fighter("e2", FactionEnemy, Cell{2, 0})
	guard.MoveRange = 1
	guard.SupportDefendCharges = 1
	state.Units = append(state.Units, supporter, guard)
	return state
}

func attackOn(target string, weapon string) Decision {
	return Decision{UnitID: "a1", Kind: ActionAttack, TargetID: target, Weapon: weapon}
}

func apply(t *testing.T, state *Board, decision Decision, dice Forced) Trace {
	t.Helper()
	trace, err := state.Apply(decision, dice)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	return trace
}

func TestTheMoveComesBeforeTheStrike(t *testing.T) {
	state := shootout()
	state.Unit("a1").MoveRange = 2
	state.Unit("e1").Footprint.Anchor = Cell{4, 0}
	anchor := Cell{1, 0}

	trace := apply(t, state, Decision{UnitID: "a1", Kind: ActionAttack, MoveTo: &anchor,
		TargetID: "e1", Weapon: "beam rifle"}, Forced{Strike: true})

	if got := state.Unit("a1").Footprint.Anchor; got != anchor {
		t.Fatalf("anchor: %v", got)
	}
	if len(trace) != 1 || trace[0].Kind != StrikeMain || !trace[0].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if state.Unit("e1").HP >= 12000 || state.Unit("a1").EN != 130 {
		t.Fatalf("the strike takes hit points and energy: %+v", state.Units)
	}
	if !state.Unit("a1").Acted {
		t.Fatal("an attack ends the activation")
	}
}

func TestAnIllegalMoveStopsTheAction(t *testing.T) {
	far := Cell{4, 4}
	near := Cell{1, 0}
	cases := map[string]struct {
		build    func(*Board)
		decision Decision
	}{
		"an anchor out of the move range": {
			func(state *Board) { state.Unit("a1").MoveRange = 1 },
			Decision{UnitID: "a1", Kind: ActionAttack, MoveTo: &far,
				TargetID: "e1", Weapon: "beam rifle"},
		},
		"a weapon that fires before the move": {
			func(state *Board) {
				state.Unit("a1").MoveRange = 2
				state.Unit("a1").Weapons[0].UsableAfterMove = false
			},
			Decision{UnitID: "a1", Kind: ActionAttack, MoveTo: &near,
				TargetID: "e1", Weapon: "beam rifle"},
		},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			state := shootout()
			one.build(state)

			_, err := state.Apply(one.decision, Forced{Strike: true})

			if !errors.Is(err, ErrIllegalMove) {
				t.Fatalf("error: %v", err)
			}
			if state.Unit("a1").Footprint.Anchor != (Cell{0, 0}) || state.Unit("a1").Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestADestroyedUnitKeepsItsPlaceWithNoHitPointsLeft(t *testing.T) {
	state := shootout()
	state.Unit("e1").HP = 1

	trace := apply(t, state, attackOn("e1", "beam rifle"), Forced{Strike: true})

	if got := state.Unit("e1"); got == nil || got.HP != 0 || got.Alive() {
		t.Fatalf("unit: %+v", got)
	}
	if !trace[0].Killed {
		t.Fatalf("trace: %+v", trace)
	}
	if len(state.ByFaction(FactionEnemy)) != 0 || len(state.Units) != 2 {
		t.Fatal("a roster query filters on Alive, and the board keeps the unit")
	}
}

func TestAKillGivesTheAttackerItsActivationAgain(t *testing.T) {
	state := shootout()
	state.Unit("e1").HP = 1
	state.Unit("a1").ChanceSteps = 1
	state.Unit("a1").ChanceStepsMax = 1

	apply(t, state, attackOn("e1", "beam rifle"), Forced{Strike: true})

	if state.Unit("a1").Acted || state.Unit("a1").ChanceSteps != 0 {
		t.Fatalf("actor: %+v", state.Unit("a1"))
	}
}

func TestAKillWithNoChanceStepLeftEndsTheActivation(t *testing.T) {
	state := shootout()
	state.Unit("e1").HP = 1

	apply(t, state, attackOn("e1", "beam rifle"), Forced{Strike: true})

	if !state.Unit("a1").Acted {
		t.Fatal("the unit holds no chance step, so the kill gives no second activation")
	}
}

func TestTheSupportDefenderTakesEveryShotAndOneCharge(t *testing.T) {
	state := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2"}
	decision.Reaction = &Reaction{Stance: StanceDodge, SupportDefender: "e2"}

	trace := apply(t, state, decision, Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 2 || trace[0].StruckID != "e2" || trace[1].StruckID != "e2" {
		t.Fatalf("every shot goes to the support defender: %+v", trace)
	}
	if state.Unit("e2").SupportDefendCharges != 0 {
		t.Fatal("every shot together spends one charge")
	}
	if state.Unit("e1").HP != 12000 {
		t.Fatal("the target takes nothing")
	}
	if state.Unit("a2").SupportAttackCharges != 0 || state.Unit("a2").EN != 130 {
		t.Fatalf("the supporter spends one charge and the energy of its weapon: %+v",
			state.Unit("a2"))
	}
}

func TestASupportAttackThatMissesSpendsNoSupportDefendCharge(t *testing.T) {
	state := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2"}
	decision.Reaction = &Reaction{Stance: StanceDodge, SupportDefender: "e2"}

	apply(t, state, decision, Forced{})

	if state.Unit("e2").SupportDefendCharges != 1 || state.Unit("e2").HP != 12000 {
		t.Fatalf("supportDefender: %+v", state.Unit("e2"))
	}
	if state.Unit("a2").SupportAttackCharges != 0 || state.Unit("a2").EN != 130 {
		t.Fatal("a supporter that misses spends its charge and its energy")
	}
}

func TestTheSupportAttackOfTheAttackerIsAChoice(t *testing.T) {
	state := covered()

	trace := apply(t, state, attackOn("e1", "beam rifle"), Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 1 || trace[0].Kind != StrikeMain {
		t.Fatalf("the action names no support attacker, so none fires: %+v", trace)
	}
	if state.Unit("a2").SupportAttackCharges != 1 {
		t.Fatal("the supporter keeps its charge")
	}
}

func TestTheRulesCapTheNumberOfSupportAttackers(t *testing.T) {
	state := covered()
	names := []string{"a2"}
	for index := 0; index <= MaxSupportAttackers; index++ {
		joining := fighter(fmt.Sprintf("a%d", index+3), FactionAlly, Cell{2, index + 1})
		joining.Weapons = []Weapon{beam()}
		joining.MoveRange = 3
		joining.SupportAttackCharges = 1
		state.Units = append(state.Units, joining)
		names = append(names, joining.ID)
	}
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = names

	_, err := state.Apply(decision, Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("the cap of the rules is %d units: %v", MaxSupportAttackers, err)
	}
	for _, name := range names {
		if state.Unit(name).SupportAttackCharges != 1 {
			t.Fatalf("an error leaves the board as it was: %q", name)
		}
	}
}

func TestTheDefenderRepliesWithItsSupportAndItsCounter(t *testing.T) {
	state := covered()
	state.Unit("e2").SupportAttackCharges = 1
	state.Unit("e2").Weapons = []Weapon{beam()}
	decision := attackOn("e1", "beam rifle")
	decision.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle",
		SupportAttackers: []string{"e2"}}

	trace := apply(t, state, decision, Forced{DefenderSupport: true, Strike: true, Counter: true})

	kinds := []StrikeKind{trace[0].Kind, trace[1].Kind, trace[2].Kind}
	want := []StrikeKind{StrikeMain, StrikeDefenderSupport, StrikeCounter}
	if len(trace) != 3 || kinds[0] != want[0] || kinds[1] != want[1] || kinds[2] != want[2] {
		t.Fatalf("the support attack of the defender comes before its counter: %+v", trace)
	}
	if !trace[1].Landed {
		t.Fatal("the support attack of the defender reads the node of its own side")
	}
	if state.Unit("a1").HP >= 12000 || state.Unit("e1").EN != 130 {
		t.Fatalf("attacker: %+v", state.Unit("a1"))
	}
}

func TestACounterThatMissesSpendsItsEnergy(t *testing.T) {
	state := shootout()
	decision := attackOn("e1", "beam rifle")
	decision.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle"}

	trace := apply(t, state, decision, Forced{Strike: true})

	if len(trace) != 2 || trace[1].Kind != StrikeCounter || trace[1].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if state.Unit("e1").EN != 130 || state.Unit("a1").HP != 12000 {
		t.Fatalf("the weapon spends its energy on a miss: %+v", state.Unit("e1"))
	}
}

func TestADeadTargetRepliesWithNothing(t *testing.T) {
	state := shootout()
	state.Unit("e1").HP = 1
	decision := attackOn("e1", "beam rifle")
	decision.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle"}

	trace := apply(t, state, decision, Forced{Strike: true, Counter: true})

	if len(trace) != 1 || state.Unit("a1").HP != 12000 {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheSupportDefendWhenAttackTakesTheCounterForTheAttacker(t *testing.T) {
	state := shootout()
	bearer := fighter("a2", FactionAlly, Cell{0, 1})
	bearer.MoveRange = 1
	bearer.SupportDefendWhenAttack = true
	bearer.SupportDefendCharges = 1
	state.Units = append(state.Units, bearer)
	decision := attackOn("e1", "beam rifle")
	decision.SupportDefender = "a2"
	decision.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle"}

	trace := apply(t, state, decision, Forced{Strike: true, Counter: true})

	if trace[1].StruckID != "a2" || state.Unit("a1").HP != 12000 {
		t.Fatalf("the bearer takes the counter: %+v", trace)
	}
	if state.Unit("a2").SupportDefendCharges != 0 || state.Unit("a2").HP >= 12000 {
		t.Fatalf("bearer: %+v", state.Unit("a2"))
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
			state := shootout()
			state.Unit("a1").Weapons = []Weapon{net}
			state.Unit("e1").Debuffs = []Debuff{
				{Kind: "mobility_down", Magnitude: 0.3, AppliedPhase: 1},
				{Kind: "armor_break", Magnitude: one.start, AppliedPhase: 1},
			}

			apply(t, state, attackOn("e1", "wire net"), Forced{Strike: true})

			debuffs := state.Unit("e1").Debuffs
			if len(debuffs) != 2 {
				t.Fatalf("debuffs: %+v", debuffs)
			}
			last := debuffs[len(debuffs)-1]
			if last.Kind != "armor_break" || last.Magnitude != one.want {
				t.Fatalf("debuffs: %+v", debuffs)
			}
			if one.start != one.want && last.AppliedPhase != state.PhaseIndex() {
				t.Fatalf("a fresh debuff carries the phase of this strike: %+v", last)
			}
		})
	}
}

func TestAMapAttackIsRefusedAndLeavesTheBoard(t *testing.T) {
	state := shootout()
	shells := beam()
	shells.Name, shells.MapWeapon, shells.ENCost = "shells", true, 5
	state.Unit("a1").Weapons = []Weapon{shells}
	state.Unit("a1").Ammo = map[string]int{"shells": 2}
	aim := Cell{3, 0}

	_, err := state.Apply(Decision{UnitID: "a1", Kind: ActionMapAttack,
		Weapon: "shells", Aim: &aim}, Forced{Strike: true})

	if !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("the engine resolves no map attack: %v", err)
	}
	if state.Unit("e1").HP != 12000 || state.Unit("a1").Ammo["shells"] != 2 ||
		state.Unit("a1").Acted {
		t.Fatalf("the refused action changes no field: %+v", state.Unit("a1"))
	}
}

func TestASkillIsRefusedAndLeavesTheBoard(t *testing.T) {
	state := shootout()
	state.Unit("a1").HP = 8000
	state.Unit("a1").Skills = []Skill{{Kind: "skill_heal", Uses: 1}}

	_, err := state.Apply(Decision{UnitID: "a1", Kind: "skill_heal"}, Forced{Strike: true})

	if !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("the engine resolves no skill: %v", err)
	}
	if state.Unit("a1").HP != 8000 || state.Unit("a1").Skills[0].Uses != 1 ||
		state.Unit("a1").Acted {
		t.Fatalf("the refused action changes no field: %+v", state.Unit("a1"))
	}
}

type probes map[Node]float64

func (p probes) Lands(node Node, probability float64) bool {
	p[node] = probability
	return true
}

func TestAStrikeNamesALivingFoeAndNoOtherUnit(t *testing.T) {
	cases := map[string]string{"an ally": "a2", "the actor itself": "a1"}

	for name, target := range cases {
		t.Run(name, func(t *testing.T) {
			state := shootout()
			state.Units = append(state.Units, fighter("a2", FactionAlly, Cell{1, 0}))

			_, err := state.Apply(attackOn(target, "beam rifle"), Forced{Strike: true})

			if !errors.Is(err, ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if state.Unit(target).HP != 12000 {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAReactionThatBreaksARuleIsAnError(t *testing.T) {
	cases := map[string]Reaction{
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

	for name, reaction := range cases {
		t.Run(name, func(t *testing.T) {
			state := covered()
			decision := attackOn("e1", "beam rifle")
			decision.Reaction = &reaction

			_, err := state.Apply(decision, Forced{Strike: true})

			if !errors.Is(err, ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if state.Unit("e1").HP != 12000 || state.Unit("a1").Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAStrikeWithNoReactionAndOneWithACounterBothRun(t *testing.T) {
	state := shootout()
	counter := attackOn("e1", "beam rifle")
	counter.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle"}

	apply(t, state, counter, Forced{Strike: true, Counter: true})

	state = shootout()
	apply(t, state, attackOn("e1", "beam rifle"), Forced{Strike: true})

	if state.Unit("e1").HP >= 12000 {
		t.Fatal("a strike that carries no reaction stays legal")
	}
}

func TestTheHitRateOfTheStrikeReadsTheTargetAndNotTheCover(t *testing.T) {
	state := covered()
	state.Unit("e2").Mech.Mobility = 900
	state.Unit("e2").Pilot.Reaction = 900
	decision := attackOn("e1", "beam rifle")
	decision.Reaction = &Reaction{Stance: StanceDodge, SupportDefender: "e2"}
	nodes := probes{}

	trace, err := state.Apply(decision, nodes)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}

	weapon := beam()
	want := StrikeHitProbability(state.Unit("a1"), state.Unit("e1"), &weapon, true)
	if trace[0].StruckID != "e2" {
		t.Fatalf("the support defender takes the strike: %+v", trace)
	}
	if nodes[NodeStrike] != want {
		t.Fatalf("hit rate: %v, and the target gives %v", nodes[NodeStrike], want)
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
			state := shootout()
			shells := beam()
			shells.Name, shells.MapWeapon = "shells", true
			state.Unit("a1").Weapons = append(state.Unit("a1").Weapons, shells)
			state.Units = append(state.Units, fighter("e2", FactionEnemy, Cell{4, 4}))

			if _, err := state.Apply(decision, Forced{Strike: true}); err == nil {
				t.Fatal("the action stands outside the board")
			}
		})
	}
}

func TestAnUnpaidWeaponAndAnEmptyCounterAreErrors(t *testing.T) {
	state := shootout()
	state.Unit("a1").EN = 9
	if _, err := state.Apply(attackOn("e1", "beam rifle"), Forced{}); !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}

	state = shootout()
	state.Unit("e1").Weapons[0].CanCounter = false
	decision := attackOn("e1", "beam rifle")
	decision.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle"}

	_, err := state.Apply(decision, Forced{Strike: true})

	if !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if state.Unit("e1").HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestAUnitThatCannotActRunsNoAction(t *testing.T) {
	state := shootout()
	state.Unit("a1").Acted = true

	_, err := state.Apply(attackOn("e1", "beam rifle"), Forced{Strike: true})

	if !errors.Is(err, ErrActed) {
		t.Fatalf("error: %v", err)
	}
}

func TestAStandbyEndsTheActivationAndAsksNoDie(t *testing.T) {
	state := shootout()

	trace := apply(t, state, Decision{UnitID: "a1", Kind: ActionStandby}, Forced{})

	if len(trace) != 0 || !state.Unit("a1").Acted {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheAttackerNamesAUnitThatCanTakeTheCounterForIt(t *testing.T) {
	state := shootout()
	plain := fighter("a2", FactionAlly, Cell{0, 1})
	plain.MoveRange = 1
	plain.SupportDefendCharges = 1
	state.Units = append(state.Units, plain)
	decision := attackOn("e1", "beam rifle")
	decision.SupportDefender = "a2"
	decision.Reaction = &Reaction{Stance: StanceCounter, Weapon: "beam rifle"}

	_, err := state.Apply(decision, Forced{Strike: true, Counter: true})

	if !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("a unit with no attack shield takes no counter for its side: %v", err)
	}
	if state.Unit("a1").Acted || state.Unit("e1").HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestASupportAttackerJoinsOneStrikeOneTime(t *testing.T) {
	state := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2", "a2"}

	_, err := state.Apply(decision, Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if state.Unit("a2").SupportAttackCharges != 1 {
		t.Fatal("an error leaves the board as it was")
	}
}
