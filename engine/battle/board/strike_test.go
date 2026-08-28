package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func fighter(id string, faction faction, anchor cell) Unit {
	out := unit(id, faction, anchor)
	out.HP, out.MaxHP = 12000, 12000
	out.EN, out.ENMax = 140, 140
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func beam() Weapon {
	out := rifle("beam rifle", radiusRange{Min: 1, Max: 3})
	out.Power, out.Accuracy, out.ENCost = 1800, 5, 10
	return out
}

func TestTheDamageOfOneShotReadsTheStanceAndTheDebuffs(t *testing.T) {
	attacker := fighter("a1", factionAlly, cell{0, 0})
	defender := fighter("e1", factionEnemy, cell{2, 0})
	weapon := beam()

	plain := StrikeDamage(&attacker, &defender, &weapon, NoDefenseMultiplier)
	defended := StrikeDamage(&attacker, &defender, &weapon, DefendMultiplier)
	defender.Debuffs = []debuff{{Kind: "armor_break", Magnitude: 0.2}}
	broken := StrikeDamage(&attacker, &defender, &weapon, NoDefenseMultiplier)

	if plain <= 0 || defended <= 0 {
		t.Fatalf("damage: %d %d", plain, defended)
	}
	if defended >= plain {
		t.Fatalf("a defended shot takes less: %d against %d", defended, plain)
	}
	if broken <= plain {
		t.Fatalf("a debuff of 0.2 raises the damage: %d against %d", broken, plain)
	}
}

func TestTheDamageRoundsAHalfToTheEvenInteger(t *testing.T) {
	blank := Unit{}
	scale := CombatBaseDamage(Weapon{Power: 1}, &blank, &blank, NoTerrainCorrection)
	low := Weapon{Power: 2.5 / scale}
	high := Weapon{Power: 3.5 / scale}

	raw := ExpectedDamage(low, &blank, &blank, NoTerrainCorrection, 0, 0, NoDefenseMultiplier)
	if raw != 2.5 {
		t.Fatalf("the constructed value is %v, and the test needs a half", raw)
	}
	if got := StrikeDamage(&blank, &blank, &low, NoDefenseMultiplier); got != 2 {
		t.Fatalf("2.5 rounds to 2, not to %d", got)
	}
	if got := StrikeDamage(&blank, &blank, &high, NoDefenseMultiplier); got != 4 {
		t.Fatalf("3.5 rounds to 4, not to %d", got)
	}
}

func TestTheDodgeOfTheDefenderCostsTheAttackerItsHitRate(t *testing.T) {
	attacker := fighter("a1", factionAlly, cell{0, 0})
	defender := fighter("e1", factionEnemy, cell{2, 0})
	weapon := beam()

	plain := StrikeHitProbability(&attacker, &defender, &weapon, false)
	dodged := StrikeHitProbability(&attacker, &defender, &weapon, true)

	if plain != HitProbability(weapon, &attacker, &defender, 0) {
		t.Fatalf("a shot that meets no dodge carries no correction: %v", plain)
	}
	if dodged != HitProbability(weapon, &attacker, &defender, -DodgeHitPenalty) {
		t.Fatalf("a dodge takes the penalty of the rules off the rate: %v", dodged)
	}
}

func TestTheStanceMultiplierOfEveryStance(t *testing.T) {
	plain := fighter("d1", factionAlly, cell{0, 0})
	shielded := fighter("d2", factionAlly, cell{0, 1})
	shielded.HasShield = true

	want := map[stance]float64{
		stanceDefend:  DefendMultiplier,
		stanceDodge:   NoDefenseMultiplier,
		stanceCounter: NoDefenseMultiplier,
		stanceNone:    NoDefenseMultiplier,
	}
	for stance, multiplier := range want {
		if got := StanceMultiplier(stance, &plain); got != multiplier {
			t.Errorf("%q: %v against %v", stance, got, multiplier)
		}
	}
	if got := StanceMultiplier(stanceDefend, &shielded); got != ShieldMultiplier*DefendMultiplier {
		t.Errorf("a defender that carries a shield pays both cuts: %v", got)
	}
	if got := StanceMultiplier(stanceDodge, &shielded); got != NoDefenseMultiplier {
		t.Errorf("a shield answers no dodge: %v", got)
	}
}

func TestTheCounterWeaponNeedsTheReachTheEnergyAndThePermission(t *testing.T) {
	defender := fighter("d1", factionAlly, cell{0, 0})
	costly := beam()
	costly.Name, costly.ENCost = "costly", 200
	passive := beam()
	passive.Name, passive.CanCounter = "net", false
	shells := beam()
	shells.Name, shells.MapWeapon = "shells", true
	near := rifle("saber", radiusRange{Min: 1, Max: 1})
	defender.Mech.Weapons = []Weapon{costly, passive, shells, beam(), near}
	state := board(defender, fighter("e1", factionEnemy, cell{2, 0}))

	attacker := state.unit("e1").Footprint
	first := state.counterWeapon(state.unit("d1"), "", attacker)
	named := state.counterWeapon(state.unit("d1"), "saber", attacker)
	unpaid := state.counterWeapon(state.unit("d1"), "costly", attacker)

	if first == nil || first.Name != "beam rifle" {
		t.Fatalf("an empty name takes the first weapon that fits: %+v", first)
	}
	if named != nil {
		t.Fatalf("the saber reaches one cell, and the attacker stands two away: %+v", named)
	}
	if unpaid != nil {
		t.Fatalf("a weapon that the unit cannot pay for counters nothing: %+v", unpaid)
	}
}

func TestForcedDiceAnswerByNode(t *testing.T) {
	dice := battle.Forced{AttackerSupport: true, Strike: false, Counter: true}

	if !dice.Lands(battle.NodeAttackerSupport, 0) || dice.Lands(battle.NodeStrike, 1) ||
		!dice.Lands(battle.NodeCounter, 0.5) {
		t.Fatal("each node reads its own outcome, and no node reads the probability")
	}
}
