package engagement

import (
	"errors"
	"fmt"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func named(id string) *string {
	return &id
}

func shootoutUnits() []battle.Unit {
	attacker := fighter("a1", battle.FactionAlly, battle.Cell{0, 0})
	attacker.Mech.Weapons = []battle.Weapon{beam()}
	target := fighter("e1", battle.FactionEnemy, battle.Cell{3, 0})
	target.Mech.Weapons = []battle.Weapon{beam()}
	return []battle.Unit{attacker, target}
}

func shootout() *state.Battle {
	return board(shootoutUnits()...)
}

func coveredUnits() []battle.Unit {
	supporter := fighter("a2", battle.FactionAlly, battle.Cell{1, 1})
	supporter.Mech.Weapons = []battle.Weapon{beam()}
	supporter.Mech.MoveRange = 2
	supporter.SupportAttackCharges = 1
	guard := fighter("e2", battle.FactionEnemy, battle.Cell{2, 0})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	return append(shootoutUnits(), supporter, guard)
}

func covered() *state.Battle {
	return board(coveredUnits()...)
}

func attackOn(target string, weapon string) battle.Decision {
	return battle.Decision{UnitID: "a1", Kind: battle.ActionAttack, TargetID: &target, Weapon: &weapon}
}

func resolve(b *state.Battle, decision battle.Decision, dice battle.Dice) (Trace, error) {
	plan, err := Prepare(b, decision)
	if err != nil {
		return nil, err
	}
	return Commit(b, plan, dice), nil
}

func apply(t *testing.T, b *state.Battle, decision battle.Decision, dice battle.Dice) Trace {
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
	b.Unit("e1").Value.Pos = battle.Cell{4, 0}
	anchor := battle.Cell{1, 0}

	trace := apply(t, b, battle.Decision{UnitID: "a1", Kind: battle.ActionAttack, MoveTo: &anchor,
		TargetID: named("e1"), Weapon: named("beam rifle")}, battle.Forced{Strike: true})

	if got := b.Unit("a1").Value.Pos; got != anchor {
		t.Fatalf("anchor: %v", got)
	}
	if len(trace) != 1 || trace[0].Kind != StrikeMain || !trace[0].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if b.Unit("e1").Value.HP >= 12000 || b.Unit("a1").Value.EN != 130 {
		t.Fatalf("the strike takes hit points and energy: %+v", b.Units)
	}
	if !b.Unit("a1").Value.Acted {
		t.Fatal("an attack ends the activation")
	}
}

func TestAnIllegalMoveStopsTheAction(t *testing.T) {
	far := battle.Cell{4, 4}
	near := battle.Cell{1, 0}
	cases := map[string]struct {
		build    func(*state.Battle)
		decision battle.Decision
	}{
		"an anchor out of the move range": {
			func(b *state.Battle) { b.Unit("a1").Mech.MoveRange = 1 },
			battle.Decision{UnitID: "a1", Kind: battle.ActionAttack, MoveTo: &far,
				TargetID: named("e1"), Weapon: named("beam rifle")},
		},
		"a weapon that fires before the move": {
			func(b *state.Battle) {
				b.Unit("a1").Mech.MoveRange = 2
				b.Unit("a1").Mech.Weapons[0].UsableAfterMove = false
			},
			battle.Decision{UnitID: "a1", Kind: battle.ActionAttack, MoveTo: &near,
				TargetID: named("e1"), Weapon: named("beam rifle")},
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
			if b.Unit("a1").Value.Pos != (battle.Cell{0, 0}) || b.Unit("a1").Value.Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestADestroyedUnitKeepsItsPlaceWithNoHitPointsLeft(t *testing.T) {
	b := shootout()
	b.Unit("e1").Value.HP = 1

	trace := apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if got := b.Unit("e1"); got == nil || got.Value.HP != 0 || got.Alive() {
		t.Fatalf("unit: %+v", got)
	}
	if !trace[0].Killed {
		t.Fatalf("trace: %+v", trace)
	}
	if len(byFaction(b, battle.FactionEnemy)) != 0 || len(b.Units) != 2 {
		t.Fatal("a roster query filters on Alive, and the board keeps the unit")
	}
}

func TestAKillGivesTheAttackerItsActivationAgain(t *testing.T) {
	b := shootout()
	b.Unit("e1").Value.HP = 1
	b.Unit("a1").Value.ChanceSteps = 1
	b.Unit("a1").ChanceStepsMax = 1

	apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if b.Unit("a1").Value.Acted || b.Unit("a1").Value.ChanceSteps != 0 {
		t.Fatalf("actor: %+v", b.Unit("a1"))
	}
}

func TestAKillWithNoChanceStepLeftEndsTheActivation(t *testing.T) {
	b := shootout()
	b.Unit("e1").Value.HP = 1

	apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if !b.Unit("a1").Value.Acted {
		t.Fatal("the unit holds no chance step, so the kill gives no second activation")
	}
}

func TestTheSupportDefenderTakesEveryShotAndOneCharge(t *testing.T) {
	b := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2"}
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge, SupportDefender: named("e2")}

	trace := apply(t, b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 2 || trace[0].StruckID != "e2" || trace[1].StruckID != "e2" {
		t.Fatalf("every shot goes to the support defender: %+v", trace)
	}
	if b.Unit("e2").Value.SupportDefendCharges != 0 {
		t.Fatal("every shot together spends one charge")
	}
	if b.Unit("e1").Value.HP != 12000 {
		t.Fatal("the target takes nothing")
	}
	if b.Unit("a2").Value.SupportAttackCharges != 0 || b.Unit("a2").Value.EN != 130 {
		t.Fatalf("the supporter spends one charge and the energy of its weapon: %+v",
			b.Unit("a2"))
	}
}

func TestASupportAttackThatMissesSpendsNoSupportDefendCharge(t *testing.T) {
	b := covered()
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = []string{"a2"}
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge, SupportDefender: named("e2")}

	apply(t, b, decision, battle.Forced{})

	if b.Unit("e2").Value.SupportDefendCharges != 1 || b.Unit("e2").Value.HP != 12000 {
		t.Fatalf("supportDefender: %+v", b.Unit("e2"))
	}
	if b.Unit("a2").Value.SupportAttackCharges != 0 || b.Unit("a2").Value.EN != 130 {
		t.Fatal("a supporter that misses spends its charge and its energy")
	}
}

func TestTheSupportAttackOfTheAttackerIsAChoice(t *testing.T) {
	b := covered()

	trace := apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 1 || trace[0].Kind != StrikeMain {
		t.Fatalf("the action names no support attacker, so none fires: %+v", trace)
	}
	if b.Unit("a2").Value.SupportAttackCharges != 1 {
		t.Fatal("the supporter keeps its charge")
	}
}

func TestTheRulesCapTheNumberOfSupportAttackers(t *testing.T) {
	units := coveredUnits()
	names := []string{"a2"}
	for index := 0; index <= maxSupportAttackers; index++ {
		joining := fighter(fmt.Sprintf("a%d", index+3), battle.FactionAlly, battle.Cell{2, index + 1})
		joining.Mech.Weapons = []battle.Weapon{beam()}
		joining.Mech.MoveRange = 3
		joining.SupportAttackCharges = 1
		units = append(units, joining)
		names = append(names, joining.ID)
	}
	b := board(units...)
	decision := attackOn("e1", "beam rifle")
	decision.SupportAttackers = names

	_, err := resolve(b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the cap of the rules is %d units: %v", maxSupportAttackers, err)
	}
	for _, name := range names {
		if b.Unit(name).Value.SupportAttackCharges != 1 {
			t.Fatalf("an error leaves the board as it was: %q", name)
		}
	}
}

func TestTheDefenderRepliesWithItsSupportAndItsCounter(t *testing.T) {
	units := coveredUnits()
	guard := unitIn(units, "e2")
	guard.SupportAttackCharges = 1
	guard.Mech.Weapons = []battle.Weapon{beam()}
	b := board(units...)
	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle"),
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
	if b.Unit("a1").Value.HP >= 12000 || b.Unit("e1").Value.EN != 130 {
		t.Fatalf("attacker: %+v", b.Unit("a1"))
	}
}

// Protocol 1.5 retired the permission 'can_counter': a weapon counters under
// the rule of an attack, so every weapon that reaches the attacker and holds
// its energy stands in the menu and fires.
func TestEveryWeaponThatReachesTheAttackerCounters(t *testing.T) {
	units := shootoutUnits()
	pod := beam()
	pod.Name = "missile pod"
	target := unitIn(units, "e1")
	target.Mech.Weapons = append(target.Mech.Weapons, pod)
	b := board(units...)

	options, err := Menu(b, attackOn("e1", "beam rifle"), "e1")
	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}
	var offered []string
	for _, option := range options.ResponseAttacks {
		if option.Stance == battle.StanceCounter {
			offered = append(offered, option.Weapon)
		}
	}
	if len(offered) != 2 || offered[0] != "beam rifle" || offered[1] != "missile pod" {
		t.Fatalf("counters: %v", offered)
	}

	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("missile pod")}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	last := trace[len(trace)-1]
	if last.Kind != StrikeCounter || last.Weapon != "missile pod" || !last.Landed {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestACounterThatMissesSpendsItsEnergy(t *testing.T) {
	b := shootout()
	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}

	trace := apply(t, b, decision, battle.Forced{Strike: true})

	if len(trace) != 2 || trace[1].Kind != StrikeCounter || trace[1].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if b.Unit("e1").Value.EN != 130 || b.Unit("a1").Value.HP != 12000 {
		t.Fatalf("the weapon spends its energy on a miss: %+v", b.Unit("e1"))
	}
}

func TestADeadTargetRepliesWithNothing(t *testing.T) {
	b := shootout()
	b.Unit("e1").Value.HP = 1
	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	if len(trace) != 1 || b.Unit("a1").Value.HP != 12000 {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheSupportDefendWhenAttackTakesTheCounterForTheAttacker(t *testing.T) {
	bearer := fighter("a2", battle.FactionAlly, battle.Cell{0, 1})
	bearer.Mech.MoveRange = 1
	bearer.SupportDefendWhenAttack = true
	bearer.SupportDefendCharges = 1
	b := board(append(shootoutUnits(), bearer)...)
	decision := attackOn("e1", "beam rifle")
	decision.SupportDefender = named("a2")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	if trace[1].StruckID != "a2" || b.Unit("a1").Value.HP != 12000 {
		t.Fatalf("the bearer takes the counter: %+v", trace)
	}
	if b.Unit("a2").Value.SupportDefendCharges != 0 || b.Unit("a2").Value.HP >= 12000 {
		t.Fatalf("bearer: %+v", b.Unit("a2"))
	}
}

func TestADebuffReplacesAWeakerOneAndLeavesAStrongerOne(t *testing.T) {
	kind := "armor_break"
	net := beam()
	net.Name, net.DebuffKind, net.DebuffMagnitude = "wire net", &kind, 0.2
	cases := map[string]struct {
		start float64
		want  float64
	}{"weaker": {0.1, 0.2}, "stronger": {0.5, 0.5}}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			units := shootoutUnits()
			unitIn(units, "a1").Mech.Weapons = []battle.Weapon{net}
			unitIn(units, "e1").Debuffs = []battle.Debuff{
				{Kind: "mobility_down", Magnitude: 0.3, AppliedPhase: 1},
				{Kind: "armor_break", Magnitude: one.start, AppliedPhase: 1},
			}
			b := board(units...)

			apply(t, b, attackOn("e1", "wire net"), battle.Forced{Strike: true})

			debuffs := b.Unit("e1").Value.Debuffs
			if len(debuffs) != 2 {
				t.Fatalf("debuffs: %+v", debuffs)
			}
			last := debuffs[len(debuffs)-1]
			if last.Kind != "armor_break" || last.Magnitude != one.want {
				t.Fatalf("debuffs: %+v", debuffs)
			}
			if one.start != one.want && last.AppliedPhase != b.PhaseIndex() {
				t.Fatalf("a fresh debuff carries the phase of this strike: %+v", last)
			}
		})
	}
}

func TestAMapAttackIsRefusedAndLeavesTheBoard(t *testing.T) {
	units := shootoutUnits()
	actor := unitIn(units, "a1")
	actor.Mech.MapWeapons = []battle.MapWeapon{mapShells()}
	actor.Ammo = map[string]int{"shells": 2}
	b := board(units...)
	aim := battle.Cell{3, 0}

	_, err := resolve(b, battle.Decision{UnitID: "a1", Kind: battle.ActionMapAttack,
		Weapon: named("shells"), Aim: &aim}, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the engine resolves no map attack: %v", err)
	}
	if b.Unit("e1").Value.HP != 12000 || b.Unit("a1").Value.Ammo["shells"] != 2 ||
		b.Unit("a1").Value.Acted {
		t.Fatalf("the refused action changes no field: %+v", b.Unit("a1"))
	}
}

func TestASkillIsRefusedAndLeavesTheBoard(t *testing.T) {
	b := shootout()
	b.Unit("a1").Value.HP = 8000
	b.Unit("a1").Value.Skills = []def.Skill{{Kind: "skill_heal", Uses: 1}}

	_, err := resolve(b, battle.Decision{UnitID: "a1", Kind: "skill_heal"}, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the engine resolves no skill: %v", err)
	}
	if b.Unit("a1").Value.HP != 8000 || b.Unit("a1").Value.Skills[0].Uses != 1 ||
		b.Unit("a1").Value.Acted {
		t.Fatalf("the refused action changes no field: %+v", b.Unit("a1"))
	}
}

type probes map[battle.Node]float64

func (p probes) Lands(node battle.Node, probability float64) bool {
	p[node] = probability
	return true
}

func (p probes) Covers(int) bool {
	return true
}

func TestAStrikeNamesALivingFoeAndNoOtherUnit(t *testing.T) {
	cases := map[string]string{"an ally": "a2", "the actor itself": "a1"}

	for name, target := range cases {
		t.Run(name, func(t *testing.T) {
			b := board(append(shootoutUnits(),
				fighter("a2", battle.FactionAlly, battle.Cell{1, 0}))...)

			_, err := resolve(b, attackOn(target, "beam rifle"), battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Unit(target).Value.HP != 12000 {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAResponseAttackThatBreaksARuleIsAnError(t *testing.T) {
	cases := map[string]battle.ResponseAttack{
		"a defense that takes a support defender as well": {Stance: battle.StanceDefend,
			SupportDefender: named("e2")},
		"a unit of the other side as the support defender": {Stance: battle.StanceDodge,
			SupportDefender: named("a2")},
		"a support attacker that reaches nothing": {Stance: battle.StanceDodge,
			SupportAttackers: []string{"e2"}},
		"a weapon on a stance that fires none": {Stance: battle.StanceDodge, Weapon: named("beam rifle")},
		"a counter with a weapon the unit does not carry": {Stance: battle.StanceCounter,
			Weapon: named("wire net")},
	}

	for name, response := range cases {
		t.Run(name, func(t *testing.T) {
			b := covered()
			decision := attackOn("e1", "beam rifle")
			decision.ResponseAttack = &response

			_, err := resolve(b, decision, battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Unit("e1").Value.HP != 12000 || b.Unit("a1").Value.Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAStrikeWithNoResponseAttackAndOneWithACounterBothRun(t *testing.T) {
	b := shootout()
	counter := attackOn("e1", "beam rifle")
	counter.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}

	apply(t, b, counter, battle.Forced{Strike: true, Counter: true})

	b = shootout()
	apply(t, b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if b.Unit("e1").Value.HP >= 12000 {
		t.Fatal("a strike that carries no response attack stays legal")
	}
}

func TestTheHitRateOfTheStrikeReadsTheTargetAndNotTheCover(t *testing.T) {
	b := covered()
	b.Unit("e2").Mech.Mobility = 900
	b.Unit("e2").Pilot.Reaction = 900
	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge, SupportDefender: named("e2")}
	nodes := probes{}

	trace, err := resolve(b, decision, nodes)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}

	want := strikeHitProbability(b.Unit("a1"), b.Unit("e1"),
		&b.Unit("a1").Mech.Weapons[0], true)
	if trace[0].StruckID != "e2" {
		t.Fatalf("the support defender takes the strike: %+v", trace)
	}
	if nodes[battle.NodeStrike] != want {
		t.Fatalf("hit rate: %v, and the target gives %v", nodes[battle.NodeStrike], want)
	}
}

func TestAnActionOutsideTheBoardIsAnError(t *testing.T) {
	cases := map[string]battle.Decision{
		"an unknown unit":   {UnitID: "ghost", Kind: battle.ActionStandby},
		"an unknown target": attackOn("ghost", "beam rifle"),
		"an unknown weapon": attackOn("e1", "lance"),
		"a map weapon on an attack": {UnitID: "a1", Kind: battle.ActionAttack,
			TargetID: named("e1"), Weapon: named("shells")},
		"a weapon out of its band": {UnitID: "a1", Kind: battle.ActionAttack,
			TargetID: named("e2"), Weapon: named("beam rifle")},
	}

	for name, decision := range cases {
		t.Run(name, func(t *testing.T) {
			units := shootoutUnits()
			unitIn(units, "a1").Mech.MapWeapons = []battle.MapWeapon{mapShells()}
			b := board(append(units,
				fighter("e2", battle.FactionEnemy, battle.Cell{4, 4}))...)

			if _, err := resolve(b, decision, battle.Forced{Strike: true}); err == nil {
				t.Fatal("the action stands outside the board")
			}
		})
	}
}

func TestAnUnpaidWeaponAndAnEmptyCounterAreErrors(t *testing.T) {
	b := shootout()
	b.Unit("a1").Value.EN = 9
	if _, err := resolve(b, attackOn("e1", "beam rifle"), battle.Forced{}); !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}

	b = shootout()
	b.Unit("e1").Mech.Weapons[0].ENCost = 1000
	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}

	_, err := resolve(b, decision, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if b.Unit("e1").Value.HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestAUnitThatCannotActRunsNoAction(t *testing.T) {
	b := shootout()
	b.Unit("a1").Value.Acted = true

	_, err := resolve(b, attackOn("e1", "beam rifle"), battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrActed) {
		t.Fatalf("error: %v", err)
	}
}

func TestAStandbyEndsTheActivationAndAsksNoDie(t *testing.T) {
	b := shootout()

	trace := apply(t, b, battle.Decision{UnitID: "a1", Kind: battle.ActionStandby}, battle.Forced{})

	if len(trace) != 0 || !b.Unit("a1").Value.Acted {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheAttackerNamesAUnitThatCanTakeTheCounterForIt(t *testing.T) {
	plain := fighter("a2", battle.FactionAlly, battle.Cell{0, 1})
	plain.Mech.MoveRange = 1
	plain.SupportDefendCharges = 1
	b := board(append(shootoutUnits(), plain)...)
	decision := attackOn("e1", "beam rifle")
	decision.SupportDefender = named("a2")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}

	_, err := resolve(b, decision, battle.Forced{Strike: true, Counter: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("a unit with no attack shield takes no counter for its side: %v", err)
	}
	if b.Unit("a1").Value.Acted || b.Unit("e1").Value.HP != 12000 {
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
	if b.Unit("a2").Value.SupportAttackCharges != 1 {
		t.Fatal("an error leaves the board as it was")
	}
}

type countingDice struct {
	inner battle.Dice
	count int
}

func (c *countingDice) Lands(node battle.Node, probability float64) bool {
	c.count++
	return c.inner.Lands(node, probability)
}

func (c *countingDice) Covers(draws int) bool {
	return c.inner.Covers(draws)
}

func repliesWithSupportAndCounter() (*state.Battle, battle.Decision) {
	units := coveredUnits()
	guard := unitIn(units, "e2")
	guard.SupportAttackCharges = 1
	guard.Mech.Weapons = []battle.Weapon{beam()}
	b := board(units...)
	decision := attackOn("e1", "beam rifle")
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle"),
		SupportAttackers: []string{"e2"}}
	return b, decision
}

func TestTheDrawsOfAPlanBoundTheDrawsOfTheCommit(t *testing.T) {
	anchor := battle.Cell{1, 0}
	cases := []struct {
		name  string
		build func() (*state.Battle, battle.Decision)
		want  int
	}{
		{"a standby", func() (*state.Battle, battle.Decision) {
			return shootout(), battle.Decision{UnitID: "a1", Kind: battle.ActionStandby}
		}, 0},
		{"a reposition", func() (*state.Battle, battle.Decision) {
			b := shootout()
			b.Unit("a1").Mech.MoveRange = 2
			return b, battle.Decision{UnitID: "a1", Kind: battle.ActionReposition, MoveTo: &anchor}
		}, 0},
		{"a strike with no reply", func() (*state.Battle, battle.Decision) {
			return shootout(), attackOn("e1", "beam rifle")
		}, 1},
		{"a strike that takes a counter", func() (*state.Battle, battle.Decision) {
			decision := attackOn("e1", "beam rifle")
			decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, Weapon: named("beam rifle")}
			return shootout(), decision
		}, 2},
		{"a strike with the support of the attacker", func() (*state.Battle, battle.Decision) {
			decision := attackOn("e1", "beam rifle")
			decision.SupportAttackers = []string{"a2"}
			decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge, SupportDefender: named("e2")}
			return covered(), decision
		}, 2},
		{"a strike that takes the support and the counter of the defender",
			repliesWithSupportAndCounter, 3},
		{"a strike that takes every node", func() (*state.Battle, battle.Decision) {
			b, decision := repliesWithSupportAndCounter()
			decision.SupportAttackers = []string{"a2"}
			return b, decision
		}, 4},
	}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			b, decision := one.build()
			plan, err := Prepare(b, decision)
			if err != nil {
				t.Fatal(err)
			}
			if plan.Draws() != one.want {
				t.Fatalf("draws: %d, want %d", plan.Draws(), one.want)
			}
			dice := &countingDice{inner: battle.Forced{}}
			Commit(b, plan, dice)
			if dice.count > plan.Draws() {
				t.Fatalf("commit drew %d times, and the bound is %d", dice.count, plan.Draws())
			}
		})
	}
}
