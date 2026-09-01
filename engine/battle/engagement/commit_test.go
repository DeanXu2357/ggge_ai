package engagement

import (
	"errors"
	"fmt"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// The two boards below stand every unit at a fixed position, and the position
// of a unit is its id.
const (
	actorID   = 0 // the ally that acts
	targetID  = 1 // the enemy that it strikes
	joinerID  = 2 // the ally that joins the strike
	bearerID  = 2 // the ally that takes a strike for the actor
	coveredBy = 3 // the enemy that takes a strike for the target
)

const beamID = 0

func shootoutUnits() []battle.Unit {
	attacker := fighter(battle.FactionAlly, battle.Cell{0, 0})
	attacker.Mech.Weapons = []battle.Weapon{beam()}
	target := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	target.Mech.Weapons = []battle.Weapon{beam()}
	return []battle.Unit{attacker, target}
}

func shootout() *state.Battle {
	return board(shootoutUnits()...)
}

func coveredUnits() []battle.Unit {
	supporter := fighter(battle.FactionAlly, battle.Cell{1, 1})
	supporter.Mech.Weapons = []battle.Weapon{beam()}
	supporter.Mech.MoveRange = 2
	supporter.SupportAttackCharges = 1
	guard := fighter(battle.FactionEnemy, battle.Cell{2, 0})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	return append(shootoutUnits(), supporter, guard)
}

func covered() *state.Battle {
	return board(coveredUnits()...)
}

func attackOn(target, weapon int) battle.Decision {
	return battle.Decision{UnitID: actorID, Kind: battle.ActionAttack,
		TargetID: idOf(target), WeaponID: idOf(weapon)}
}

func resolve(b *state.Battle, decision battle.Decision, dice battle.Dice) (Trace, error) {
	made, err := prepare(b, decision)
	if err != nil {
		return nil, err
	}
	return write(b, made, dice), nil
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
	b.Units[actorID].Mech.MoveRange = 2
	b.Units[targetID].Value.Pos = battle.Cell{4, 0}
	anchor := battle.Cell{1, 0}

	trace := apply(t, b, battle.Decision{UnitID: actorID, Kind: battle.ActionAttack, MoveTo: &anchor,
		TargetID: idOf(targetID), WeaponID: idOf(beamID)}, battle.Forced{Strike: true})

	if got := b.Units[actorID].Value.Pos; got != anchor {
		t.Fatalf("anchor: %v", got)
	}
	if len(trace) != 1 || trace[0].Kind != StrikeMain || !trace[0].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if b.Units[targetID].Value.HP >= 12000 || b.Units[actorID].Value.EN != 130 {
		t.Fatalf("the strike takes hit points and energy: %+v", b.Units)
	}
	if !b.Units[actorID].Value.Acted {
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
			func(b *state.Battle) { b.Units[actorID].Mech.MoveRange = 1 },
			battle.Decision{UnitID: actorID, Kind: battle.ActionAttack, MoveTo: &far,
				TargetID: idOf(targetID), WeaponID: idOf(beamID)},
		},
		"a weapon that fires before the move": {
			func(b *state.Battle) {
				b.Units[actorID].Mech.MoveRange = 2
				b.Units[actorID].Mech.Weapons[0].UsableAfterMove = false
			},
			battle.Decision{UnitID: actorID, Kind: battle.ActionAttack, MoveTo: &near,
				TargetID: idOf(targetID), WeaponID: idOf(beamID)},
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
			if b.Units[actorID].Value.Pos != (battle.Cell{0, 0}) || b.Units[actorID].Value.Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestADestroyedUnitKeepsItsPlaceWithNoHitPointsLeft(t *testing.T) {
	b := shootout()
	b.Units[targetID].Value.HP = 1

	trace := apply(t, b, attackOn(targetID, beamID), battle.Forced{Strike: true})

	if got := &b.Units[targetID]; got.Value.HP != 0 || got.Alive() {
		t.Fatalf("unit: %+v", got)
	}
	if !trace[0].Killed {
		t.Fatalf("trace: %+v", trace)
	}
	if len(byFaction(b, battle.FactionEnemy)) != 0 || len(b.Units) != 2 {
		t.Fatal("a roster query filters on Alive, and the board keeps the unit")
	}
}

func TestAFullTurnCycleWithAKillKeepsTheUnitOrder(t *testing.T) {
	b := covered()
	b.Units[targetID].Value.HP = 1
	before := len(b.Units)
	factions := make([]battle.Faction, before)
	for index := range b.Units {
		factions[index] = b.Units[index].Faction
	}

	apply(t, b, attackOn(targetID, beamID), battle.Forced{Strike: true})
	apply(t, b, battle.Decision{UnitID: joinerID, Kind: battle.ActionStandby}, battle.Forced{})

	if len(b.Units) != before {
		t.Fatalf("the unit slice is append only: %d against %d", len(b.Units), before)
	}
	for index := range b.Units {
		if b.Units[index].Faction != factions[index] {
			t.Fatalf("the unit %d changed side, so the order moved", index)
		}
	}
	if b.Units[targetID].Alive() || b.Units[targetID].Value.HP != 0 {
		t.Fatal("the destroyed unit keeps its place with no hit points left")
	}
}

func TestAKillGivesTheAttackerItsActivationAgain(t *testing.T) {
	b := shootout()
	b.Units[targetID].Value.HP = 1
	b.Units[actorID].Value.ChanceSteps = 1
	b.Units[actorID].ChanceStepsMax = 1

	apply(t, b, attackOn(targetID, beamID), battle.Forced{Strike: true})

	if b.Units[actorID].Value.Acted || b.Units[actorID].Value.ChanceSteps != 0 {
		t.Fatalf("actor: %+v", b.Units[actorID])
	}
}

func TestAKillWithNoChanceStepLeftEndsTheActivation(t *testing.T) {
	b := shootout()
	b.Units[targetID].Value.HP = 1

	apply(t, b, attackOn(targetID, beamID), battle.Forced{Strike: true})

	if !b.Units[actorID].Value.Acted {
		t.Fatal("the unit holds no chance step, so the kill gives no second activation")
	}
}

func TestTheSupportDefenderTakesEveryShotAndOneCharge(t *testing.T) {
	b := covered()
	decision := attackOn(targetID, beamID)
	decision.SupportAttackerIDs = []int{joinerID}
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge,
		SupportDefenderID: idOf(coveredBy)}

	trace := apply(t, b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 2 || trace[0].StruckID != coveredBy || trace[1].StruckID != coveredBy {
		t.Fatalf("every shot goes to the support defender: %+v", trace)
	}
	if b.Units[coveredBy].Value.SupportDefendCharges != 0 {
		t.Fatal("every shot together spends one charge")
	}
	if b.Units[targetID].Value.HP != 12000 {
		t.Fatal("the target takes nothing")
	}
	if b.Units[joinerID].Value.SupportAttackCharges != 0 || b.Units[joinerID].Value.EN != 130 {
		t.Fatalf("the supporter spends one charge and the energy of its weapon: %+v",
			b.Units[joinerID])
	}
}

func TestASupportAttackThatMissesSpendsNoSupportDefendCharge(t *testing.T) {
	b := covered()
	decision := attackOn(targetID, beamID)
	decision.SupportAttackerIDs = []int{joinerID}
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge,
		SupportDefenderID: idOf(coveredBy)}

	apply(t, b, decision, battle.Forced{})

	if b.Units[coveredBy].Value.SupportDefendCharges != 1 || b.Units[coveredBy].Value.HP != 12000 {
		t.Fatalf("supportDefender: %+v", b.Units[coveredBy])
	}
	if b.Units[joinerID].Value.SupportAttackCharges != 0 || b.Units[joinerID].Value.EN != 130 {
		t.Fatal("a supporter that misses spends its charge and its energy")
	}
}

func TestTheSupportAttackOfTheAttackerIsAChoice(t *testing.T) {
	b := covered()

	trace := apply(t, b, attackOn(targetID, beamID), battle.Forced{AttackerSupport: true, Strike: true})

	if len(trace) != 1 || trace[0].Kind != StrikeMain {
		t.Fatalf("the action names no support attacker, so none fires: %+v", trace)
	}
	if b.Units[joinerID].Value.SupportAttackCharges != 1 {
		t.Fatal("the supporter keeps its charge")
	}
}

func TestTheRulesCapTheNumberOfSupportAttackers(t *testing.T) {
	units := coveredUnits()
	ids := []int{joinerID}
	for index := 0; index <= maxSupportAttackers; index++ {
		joining := fighter(battle.FactionAlly, battle.Cell{2, index + 1})
		joining.Mech.Weapons = []battle.Weapon{beam()}
		joining.Mech.MoveRange = 3
		joining.SupportAttackCharges = 1
		ids = append(ids, len(units))
		units = append(units, joining)
	}
	b := board(units...)
	decision := attackOn(targetID, beamID)
	decision.SupportAttackerIDs = ids

	_, err := resolve(b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the cap of the rules is %d units: %v", maxSupportAttackers, err)
	}
	for _, id := range ids {
		if b.Units[id].Value.SupportAttackCharges != 1 {
			t.Fatalf("an error leaves the board as it was: %d", id)
		}
	}
}

func TestTheDefenderRepliesWithItsSupportAndItsCounter(t *testing.T) {
	b, decision := repliesWithSupportAndCounter()

	trace := apply(t, b, decision, battle.Forced{DefenderSupport: true, Strike: true, Counter: true})

	kinds := []StrikeKind{trace[0].Kind, trace[1].Kind, trace[2].Kind}
	want := []StrikeKind{StrikeMain, StrikeDefenderSupport, StrikeCounter}
	if len(trace) != 3 || kinds[0] != want[0] || kinds[1] != want[1] || kinds[2] != want[2] {
		t.Fatalf("the support attack of the defender comes before its counter: %+v", trace)
	}
	if !trace[1].Landed {
		t.Fatal("the support attack of the defender reads the node of its own side")
	}
	if b.Units[actorID].Value.HP >= 12000 || b.Units[targetID].Value.EN != 130 {
		t.Fatalf("attacker: %+v", b.Units[actorID])
	}
}

// Protocol 1.5 retired the permission 'can_counter': a weapon counters under
// the rule of an attack, so every weapon that reaches the attacker and holds
// its energy stands in the menu and fires.
func TestEveryWeaponThatReachesTheAttackerCounters(t *testing.T) {
	units := shootoutUnits()
	pod := beam()
	pod.Name = "missile pod"
	units[targetID].Mech.Weapons = append(units[targetID].Mech.Weapons, pod)
	content, values := pair(units...)

	options, err := Menu(content, values, attackOn(targetID, beamID), targetID)
	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}
	var offered []int
	for _, option := range options.ResponseAttacks {
		if option.Stance == battle.StanceCounter {
			offered = append(offered, *option.WeaponID)
		}
	}
	if len(offered) != 2 || offered[0] != 0 || offered[1] != 1 {
		t.Fatalf("counters: %v", offered)
	}

	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(1)}

	trace := apply(t, board(units...), decision, battle.Forced{Strike: true, Counter: true})

	last := trace[len(trace)-1]
	if last.Kind != StrikeCounter || last.WeaponID != 1 || !last.Landed {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestACounterThatMissesSpendsItsEnergy(t *testing.T) {
	b := shootout()
	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(beamID)}

	trace := apply(t, b, decision, battle.Forced{Strike: true})

	if len(trace) != 2 || trace[1].Kind != StrikeCounter || trace[1].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if b.Units[targetID].Value.EN != 130 || b.Units[actorID].Value.HP != 12000 {
		t.Fatalf("the weapon spends its energy on a miss: %+v", b.Units[targetID])
	}
}

func TestADeadTargetRepliesWithNothing(t *testing.T) {
	b := shootout()
	b.Units[targetID].Value.HP = 1
	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(beamID)}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	if len(trace) != 1 || b.Units[actorID].Value.HP != 12000 {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheSupportDefendWhenAttackTakesTheCounterForTheAttacker(t *testing.T) {
	bearer := fighter(battle.FactionAlly, battle.Cell{0, 1})
	bearer.Mech.MoveRange = 1
	bearer.SupportDefendWhenAttack = true
	bearer.SupportDefendCharges = 1
	b := board(append(shootoutUnits(), bearer)...)
	decision := attackOn(targetID, beamID)
	decision.SupportDefenderID = idOf(bearerID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(beamID)}

	trace := apply(t, b, decision, battle.Forced{Strike: true, Counter: true})

	if trace[1].StruckID != bearerID || b.Units[actorID].Value.HP != 12000 {
		t.Fatalf("the bearer takes the counter: %+v", trace)
	}
	if b.Units[bearerID].Value.SupportDefendCharges != 0 || b.Units[bearerID].Value.HP >= 12000 {
		t.Fatalf("bearer: %+v", b.Units[bearerID])
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
			units[actorID].Mech.Weapons = []battle.Weapon{net}
			units[targetID].Debuffs = []battle.Debuff{
				{Kind: "mobility_down", Magnitude: 0.3, AppliedPhase: 1},
				{Kind: "armor_break", Magnitude: one.start, AppliedPhase: 1},
			}
			b := board(units...)

			apply(t, b, attackOn(targetID, 0), battle.Forced{Strike: true})

			debuffs := b.Units[targetID].Value.Debuffs
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
	units[actorID].Mech.MapWeapons = []battle.MapWeapon{mapShells()}
	units[actorID].MapWeaponAmmo = []int{2}
	b := board(units...)
	aim := battle.Cell{3, 0}

	_, err := resolve(b, battle.Decision{UnitID: actorID, Kind: battle.ActionMapAttack,
		Aim: &aim}, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the engine resolves no map attack: %v", err)
	}
	if b.Units[targetID].Value.HP != 12000 || b.Units[actorID].Value.MapWeaponAmmo[0] != 2 ||
		b.Units[actorID].Value.Acted {
		t.Fatalf("the refused action changes no field: %+v", b.Units[actorID])
	}
}

func TestAnAttackThatFiresAMapWeaponIsRefused(t *testing.T) {
	units := shootoutUnits()
	units[actorID].Mech.MapWeapons = []battle.MapWeapon{mapShells()}
	units[actorID].MapWeaponAmmo = []int{2}
	b := board(units...)

	both := battle.Decision{UnitID: actorID, Kind: battle.ActionAttack,
		TargetID: idOf(targetID), WeaponID: idOf(beamID), MapWeaponID: idOf(0)}
	area := battle.Decision{UnitID: actorID, Kind: battle.ActionAttack,
		TargetID: idOf(targetID), MapWeaponID: idOf(0)}
	bare := battle.Decision{UnitID: actorID, Kind: battle.ActionAttack, TargetID: idOf(targetID)}

	for name, decision := range map[string]battle.Decision{
		"a weapon and a map weapon": both,
		"a map weapon alone":        area,
		"no weapon at all":          bare,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := resolve(b, decision, battle.Forced{Strike: true}); !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Units[targetID].Value.HP != 12000 || b.Units[actorID].Value.Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAnActionThatIsNoAttackFiresNoWeapon(t *testing.T) {
	b := shootout()

	decision := battle.Decision{UnitID: actorID, Kind: battle.ActionStandby, WeaponID: idOf(beamID)}

	if _, err := resolve(b, decision, battle.Forced{}); !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if b.Units[actorID].Value.Acted {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestASkillIsRefusedAndLeavesTheBoard(t *testing.T) {
	b := shootout()
	b.Units[actorID].Value.HP = 8000
	b.Units[actorID].Value.Skills = []def.Skill{{Kind: "skill_heal", Uses: 1}}

	_, err := resolve(b, battle.Decision{UnitID: actorID, Kind: "skill_heal"}, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("the engine resolves no skill: %v", err)
	}
	if b.Units[actorID].Value.HP != 8000 || b.Units[actorID].Value.Skills[0].Uses != 1 ||
		b.Units[actorID].Value.Acted {
		t.Fatalf("the refused action changes no field: %+v", b.Units[actorID])
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
	cases := []struct {
		name     string
		targetID int
	}{{"an ally", 2}, {"the actor itself", actorID}}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			b := board(append(shootoutUnits(),
				fighter(battle.FactionAlly, battle.Cell{1, 0}))...)

			_, err := resolve(b, attackOn(one.targetID, beamID), battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Units[one.targetID].Value.HP != 12000 {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAResponseAttackThatBreaksARuleIsAnError(t *testing.T) {
	cases := map[string]battle.ResponseAttack{
		"a defense that takes a support defender as well": {Stance: battle.StanceDefend,
			SupportDefenderID: idOf(coveredBy)},
		"a unit of the other side as the support defender": {Stance: battle.StanceDodge,
			SupportDefenderID: idOf(joinerID)},
		"a support attacker that reaches nothing": {Stance: battle.StanceDodge,
			SupportAttackerIDs: []int{coveredBy}},
		"a weapon on a stance that fires none": {Stance: battle.StanceDodge, WeaponID: idOf(beamID)},
		"a counter with a weapon the unit does not carry": {Stance: battle.StanceCounter,
			WeaponID: idOf(4)},
	}

	for name, response := range cases {
		t.Run(name, func(t *testing.T) {
			b := covered()
			decision := attackOn(targetID, beamID)
			decision.ResponseAttack = &response

			_, err := resolve(b, decision, battle.Forced{Strike: true})

			if !errors.Is(err, battle.ErrIllegalAction) {
				t.Fatalf("error: %v", err)
			}
			if b.Units[targetID].Value.HP != 12000 || b.Units[actorID].Value.Acted {
				t.Fatal("an error leaves the board as it was")
			}
		})
	}
}

func TestAStrikeWithNoResponseAttackAndOneWithACounterBothRun(t *testing.T) {
	b := shootout()
	counter := attackOn(targetID, beamID)
	counter.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(beamID)}

	apply(t, b, counter, battle.Forced{Strike: true, Counter: true})

	b = shootout()
	apply(t, b, attackOn(targetID, beamID), battle.Forced{Strike: true})

	if b.Units[targetID].Value.HP >= 12000 {
		t.Fatal("a strike that carries no response attack stays legal")
	}
}

func TestTheHitRateOfTheStrikeReadsTheTargetAndNotTheCover(t *testing.T) {
	b := covered()
	b.Units[coveredBy].Mech.Mobility = 900
	b.Units[coveredBy].Pilot.Reaction = 900
	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge,
		SupportDefenderID: idOf(coveredBy)}
	nodes := probes{}

	trace, err := resolve(b, decision, nodes)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}

	want := strikeHitProbability(&b.Units[actorID], &b.Units[targetID],
		&b.Units[actorID].Mech.Weapons[0], true)
	if trace[0].StruckID != coveredBy {
		t.Fatalf("the support defender takes the strike: %+v", trace)
	}
	if nodes[battle.NodeStrike] != want {
		t.Fatalf("hit rate: %v, and the target gives %v", nodes[battle.NodeStrike], want)
	}
}

func TestAnActionOutsideTheBoardIsAnError(t *testing.T) {
	cases := map[string]battle.Decision{
		"an unknown unit":   {UnitID: 9, Kind: battle.ActionStandby},
		"an unknown target": attackOn(9, beamID),
		"an unknown weapon": attackOn(targetID, 9),
		"a weapon out of its band": {UnitID: actorID, Kind: battle.ActionAttack,
			TargetID: idOf(2), WeaponID: idOf(beamID)},
	}

	for name, decision := range cases {
		t.Run(name, func(t *testing.T) {
			b := board(append(shootoutUnits(),
				fighter(battle.FactionEnemy, battle.Cell{4, 4}))...)

			if _, err := resolve(b, decision, battle.Forced{Strike: true}); err == nil {
				t.Fatal("the action stands outside the board")
			}
		})
	}
}

// The gate reads every id of the wire before the first write, so a position
// under zero and a position at the length of its list both come back as a
// refusal and never as a panic.
func TestEveryPositionOfTheWireIsBoundsChecked(t *testing.T) {
	units := coveredUnits()
	units[actorID].Mech.MapWeapons = []battle.MapWeapon{mapShells()}
	units[actorID].MapWeaponAmmo = []int{2}
	gates := []struct {
		name  string
		size  int
		write func(*battle.Decision, int)
	}{
		{"unit_id", len(units), func(d *battle.Decision, v int) { d.UnitID = v }},
		{"target_id", len(units), func(d *battle.Decision, v int) { d.TargetID = idOf(v) }},
		{"weapon_id", 1, func(d *battle.Decision, v int) { d.WeaponID = idOf(v) }},
		{"map_weapon_id", 1, func(d *battle.Decision, v int) { d.WeaponID, d.MapWeaponID = nil, idOf(v) }},
		{"support_defender_id", len(units), func(d *battle.Decision, v int) { d.SupportDefenderID = idOf(v) }},
		{"support_attacker_ids", len(units), func(d *battle.Decision, v int) { d.SupportAttackerIDs = []int{v} }},
		{"response_attack.weapon_id", 1, func(d *battle.Decision, v int) {
			d.ResponseAttack.WeaponID = idOf(v)
		}},
		{"response_attack.support_defender_id", len(units), func(d *battle.Decision, v int) {
			d.ResponseAttack.SupportDefenderID = idOf(v)
		}},
		{"response_attack.support_attacker_ids", len(units), func(d *battle.Decision, v int) {
			d.ResponseAttack.SupportAttackerIDs = []int{v}
		}},
	}

	for _, one := range gates {
		for _, position := range []int{-1, one.size} {
			t.Run(fmt.Sprintf("%s at %d", one.name, position), func(t *testing.T) {
				b := board(units...)
				decision := attackOn(targetID, beamID)
				decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter,
					WeaponID: idOf(beamID)}
				one.write(&decision, position)

				_, err := resolve(b, decision, battle.Forced{Strike: true})

				if err == nil {
					t.Fatal("a position outside its list must be a refusal")
				}
				if b.Units[targetID].Value.HP != 12000 || b.Units[actorID].Value.Acted {
					t.Fatal("a refusal leaves the board as it was")
				}
			})
		}
	}
}

func TestAnUnpaidWeaponAndAnEmptyCounterAreErrors(t *testing.T) {
	b := shootout()
	b.Units[actorID].Value.EN = 9
	if _, err := resolve(b, attackOn(targetID, beamID), battle.Forced{}); !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}

	b = shootout()
	b.Units[targetID].Mech.Weapons[0].ENCost = 1000
	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(beamID)}

	_, err := resolve(b, decision, battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if b.Units[targetID].Value.HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestAUnitThatCannotActRunsNoAction(t *testing.T) {
	b := shootout()
	b.Units[actorID].Value.Acted = true

	_, err := resolve(b, attackOn(targetID, beamID), battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrActed) {
		t.Fatalf("error: %v", err)
	}
}

func TestAStandbyEndsTheActivationAndAsksNoDie(t *testing.T) {
	b := shootout()

	trace := apply(t, b, battle.Decision{UnitID: actorID, Kind: battle.ActionStandby}, battle.Forced{})

	if len(trace) != 0 || !b.Units[actorID].Value.Acted {
		t.Fatalf("trace: %+v", trace)
	}
}

func TestTheAttackerNamesAUnitThatCanTakeTheCounterForIt(t *testing.T) {
	plain := fighter(battle.FactionAlly, battle.Cell{0, 1})
	plain.Mech.MoveRange = 1
	plain.SupportDefendCharges = 1
	b := board(append(shootoutUnits(), plain)...)
	decision := attackOn(targetID, beamID)
	decision.SupportDefenderID = idOf(bearerID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(beamID)}

	_, err := resolve(b, decision, battle.Forced{Strike: true, Counter: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("a unit with no attack shield takes no counter for its side: %v", err)
	}
	if b.Units[actorID].Value.Acted || b.Units[targetID].Value.HP != 12000 {
		t.Fatal("an error leaves the board as it was")
	}
}

func TestASupportAttackerJoinsOneStrikeOneTime(t *testing.T) {
	b := covered()
	decision := attackOn(targetID, beamID)
	decision.SupportAttackerIDs = []int{joinerID, joinerID}

	_, err := resolve(b, decision, battle.Forced{AttackerSupport: true, Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if b.Units[joinerID].Value.SupportAttackCharges != 1 {
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
	units[coveredBy].SupportAttackCharges = 1
	units[coveredBy].Mech.Weapons = []battle.Weapon{beam()}
	b := board(units...)
	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter,
		WeaponID: idOf(beamID), SupportAttackerIDs: []int{coveredBy}}
	return b, decision
}

func TestTheDrawsOfAPlanBoundTheDrawsOfTheWritePhase(t *testing.T) {
	anchor := battle.Cell{1, 0}
	cases := []struct {
		name  string
		build func() (*state.Battle, battle.Decision)
		want  int
	}{
		{"a standby", func() (*state.Battle, battle.Decision) {
			return shootout(), battle.Decision{UnitID: actorID, Kind: battle.ActionStandby}
		}, 0},
		{"a reposition", func() (*state.Battle, battle.Decision) {
			b := shootout()
			b.Units[actorID].Mech.MoveRange = 2
			return b, battle.Decision{UnitID: actorID, Kind: battle.ActionReposition, MoveTo: &anchor}
		}, 0},
		{"a strike with no reply", func() (*state.Battle, battle.Decision) {
			return shootout(), attackOn(targetID, beamID)
		}, 1},
		{"a strike that takes a counter", func() (*state.Battle, battle.Decision) {
			decision := attackOn(targetID, beamID)
			decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter,
				WeaponID: idOf(beamID)}
			return shootout(), decision
		}, 2},
		{"a strike with the support of the attacker", func() (*state.Battle, battle.Decision) {
			decision := attackOn(targetID, beamID)
			decision.SupportAttackerIDs = []int{joinerID}
			decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceDodge,
				SupportDefenderID: idOf(coveredBy)}
			return covered(), decision
		}, 2},
		{"a strike that takes the support and the counter of the defender",
			repliesWithSupportAndCounter, 3},
		{"a strike that takes every node", func() (*state.Battle, battle.Decision) {
			b, decision := repliesWithSupportAndCounter()
			decision.SupportAttackerIDs = []int{joinerID}
			return b, decision
		}, 4},
	}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			b, decision := one.build()
			made, err := prepare(b, decision)
			if err != nil {
				t.Fatal(err)
			}
			if made.draws() != one.want {
				t.Fatalf("draws: %d, want %d", made.draws(), one.want)
			}
			dice := &countingDice{inner: battle.Forced{}}
			write(b, made, dice)
			if dice.count > made.draws() {
				t.Fatalf("the write phase drew %d times, and the bound is %d",
					dice.count, made.draws())
			}
		})
	}
}

func TestTheAnsweredColumnSharesNoWritableMemoryWithTheInput(t *testing.T) {
	amount := 3000.0
	units := shootoutUnits()
	units[actorID].Mech.MapWeapons = []battle.MapWeapon{mapShells()}
	units[actorID].MapWeaponAmmo = []int{2}
	units[actorID].Skills = []battle.Skill{{Kind: "skill_heal", Amount: &amount, Uses: 2}}
	units[targetID].Debuffs = []battle.Debuff{{Kind: "mobility_down", Magnitude: 0.3, AppliedPhase: 1}}
	content, values := pair(units...)

	answer, _, err := Commit(content, values, attackOn(targetID, beamID),
		battle.Forced{Strike: true})
	if err != nil {
		t.Fatalf("commit: %v", err)
	}

	answer.Units[actorID].EN, answer.Units[actorID].Acted = 404, false
	answer.Units[actorID].MapWeaponAmmo[0] = 404
	*answer.Units[actorID].Skills[0].Amount = 404
	answer.Units[targetID].Debuffs[0].Magnitude = 404
	answer.Phase, answer.Turn = battle.FactionEnemy, 404

	if values.Units[actorID].EN != 140 || values.Units[actorID].Acted ||
		values.Units[targetID].HP != 12000 {
		t.Fatalf("the input column changed: %+v", values.Units)
	}
	if values.Units[actorID].MapWeaponAmmo[0] != 2 ||
		*values.Units[actorID].Skills[0].Amount != 3000.0 ||
		values.Units[targetID].Debuffs[0].Magnitude != 0.3 {
		t.Fatalf("a slice of the input column changed: %+v", values.Units)
	}
	if values.Phase != battle.FactionAlly || values.Turn != 1 {
		t.Fatalf("the headers of the input column changed: %+v", values)
	}
}

func TestTheAnswerOfTheCommitCarriesTheChangesOfTheActivation(t *testing.T) {
	content, values := pair(shootoutUnits()...)

	answer, trace, err := Commit(content, values, attackOn(targetID, beamID),
		battle.Forced{Strike: true})
	if err != nil {
		t.Fatalf("commit: %v", err)
	}

	if len(trace) != 1 || !trace[0].Landed {
		t.Fatalf("trace: %+v", trace)
	}
	if !answer.Units[actorID].Acted || answer.Units[actorID].EN != 130 ||
		answer.Units[targetID].HP >= 12000 {
		t.Fatalf("the answer carries the changes: %+v", answer.Units)
	}
}

func TestARefusedCommitAnswersTheErrorAndNoColumn(t *testing.T) {
	content, values := pair(shootoutUnits()...)

	answer, trace, err := Commit(content, values, attackOn(actorID, beamID),
		battle.Forced{Strike: true})

	if !errors.Is(err, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", err)
	}
	if answer.Units != nil || trace != nil {
		t.Fatalf("a refusal answers no column: %+v %+v", answer, trace)
	}
	if values.Units[actorID].Acted || values.Units[targetID].HP != 12000 {
		t.Fatalf("a refusal leaves the input column as it was: %+v", values.Units)
	}
}

func TestTheCommitRefusesADiceListThatCoversFewerDrawsThanTheAction(t *testing.T) {
	content, values := pair(shootoutUnits()...)
	decision := attackOn(targetID, beamID)
	decision.ResponseAttack = &battle.ResponseAttack{Stance: battle.StanceCounter,
		WeaponID: idOf(beamID)}

	_, _, err := Commit(content, values, decision, battle.NewManualRoll([]bool{true}))

	if !errors.Is(err, battle.ErrOutsideContract) {
		t.Fatalf("error: %v", err)
	}
}
