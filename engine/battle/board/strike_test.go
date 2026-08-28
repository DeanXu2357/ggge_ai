package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
)

func fighter(id string, faction faction, anchor cell) unit {
	out := unitAt(id, faction, anchor)
	out.HP, out.MaxHP = 12000, 12000
	out.EN, out.ENMax = 140, 140
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func beam() weapon {
	out := rifle("beam rifle", radiusRange{Min: 1, Max: 3})
	out.Power, out.Accuracy, out.ENCost = 1800, 5, 10
	return out
}

func TestTheDamageOfOneShotReadsTheStanceAndTheDebuffs(t *testing.T) {
	attacker := fighter("a1", factionAlly, cell{0, 0})
	defender := fighter("e1", factionEnemy, cell{2, 0})
	weapon := beam()

	plain := strikeDamage(&attacker, &defender, &weapon, formula.NoDefenseMultiplier)
	defended := strikeDamage(&attacker, &defender, &weapon, formula.DefendMultiplier)
	defender.Debuffs = []debuff{{Kind: "armor_break", Magnitude: 0.2}}
	broken := strikeDamage(&attacker, &defender, &weapon, formula.NoDefenseMultiplier)

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

func TestTheDodgeOfTheDefenderCostsTheAttackerItsHitRate(t *testing.T) {
	attacker := fighter("a1", factionAlly, cell{0, 0})
	defender := fighter("e1", factionEnemy, cell{2, 0})
	weapon := beam()

	plain := strikeHitProbability(&attacker, &defender, &weapon, false)
	dodged := strikeHitProbability(&attacker, &defender, &weapon, true)

	attackSide := attackerSide(&attacker, weapon)
	defendSide := defenderSide(&defender)
	if plain != formula.HitProbability(weapon.Accuracy, attackSide, defendSide, 0) {
		t.Fatalf("a shot that meets no dodge carries no correction: %v", plain)
	}
	if dodged != formula.HitProbability(weapon.Accuracy, attackSide, defendSide,
		-formula.DodgeHitPenalty) {
		t.Fatalf("a dodge takes the penalty of the rules off the rate: %v", dodged)
	}
}

func TestTheDefenseMultiplierOfEveryStance(t *testing.T) {
	plain := fighter("d1", factionAlly, cell{0, 0})
	shielded := fighter("d2", factionAlly, cell{0, 1})
	shielded.HasShield = true

	want := map[stance]float64{
		stanceDefend:  formula.DefendMultiplier,
		stanceDodge:   formula.NoDefenseMultiplier,
		stanceCounter: formula.NoDefenseMultiplier,
		stanceNone:    formula.NoDefenseMultiplier,
	}
	for stance, multiplier := range want {
		if got := defenseMultiplier(stance, &plain); got != multiplier {
			t.Errorf("%q: %v against %v", stance, got, multiplier)
		}
	}
	if got := defenseMultiplier(stanceDefend, &shielded); got !=
		formula.ShieldMultiplier*formula.DefendMultiplier {
		t.Errorf("a defender that carries a shield pays both cuts: %v", got)
	}
	if got := defenseMultiplier(stanceDodge, &shielded); got != formula.NoDefenseMultiplier {
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
	defender.Mech.Weapons = []weapon{costly, passive, shells, beam(), near}
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
