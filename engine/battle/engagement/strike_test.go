package engagement

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
)

var oneCell = battle.Cell{1, 1}

func unitAt(id string, faction battle.Faction, anchor battle.Cell) battle.Unit {
	return battle.Unit{ID: id, Faction: faction,
		Pos: anchor, Size: oneCell, HP: 100,
		Mech: battle.Mech{}, Pilot: battle.Pilot{}}
}

func board(units ...battle.Unit) *battle.BattleState {
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	return &battle.BattleState{
		Bounds: &bounds, Units: units,
		Phase: battle.FactionAlly, Turn: 1}
}

func rifle(name string, rangeMin, rangeMax int) battle.Weapon {
	return battle.Weapon{Name: name, RangeMin: rangeMin, RangeMax: rangeMax, UsableAfterMove: true}
}

func fighter(id string, faction battle.Faction, anchor battle.Cell) battle.Unit {
	out := unitAt(id, faction, anchor)
	out.HP, out.MaxHP = 12000, 12000
	out.EN, out.ENMax = 140, 140
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func beam() battle.Weapon {
	out := rifle("beam rifle", 1, 3)
	out.Power, out.Accuracy, out.ENCost = 1800, 5, 10
	return out
}

func TestTheDamageOfOneShotReadsTheStanceAndTheDebuffs(t *testing.T) {
	attacker := fighter("a1", battle.FactionAlly, battle.Cell{0, 0})
	defender := fighter("e1", battle.FactionEnemy, battle.Cell{2, 0})
	weapon := beam()

	plain := strikeDamage(&attacker, &defender, &weapon, formula.NoDefenseMultiplier)
	defended := strikeDamage(&attacker, &defender, &weapon, formula.DefendMultiplier)
	defender.Debuffs = []battle.Debuff{{Kind: "armor_break", Magnitude: 0.2}}
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
	attacker := fighter("a1", battle.FactionAlly, battle.Cell{0, 0})
	defender := fighter("e1", battle.FactionEnemy, battle.Cell{2, 0})
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
	plain := fighter("d1", battle.FactionAlly, battle.Cell{0, 0})
	shielded := fighter("d2", battle.FactionAlly, battle.Cell{0, 1})
	shielded.HasShield = true

	want := map[battle.Stance]float64{
		battle.StanceDefend:  formula.DefendMultiplier,
		battle.StanceDodge:   formula.NoDefenseMultiplier,
		battle.StanceCounter: formula.NoDefenseMultiplier,
		battle.StanceNone:    formula.NoDefenseMultiplier,
	}
	for stance, multiplier := range want {
		if got := defenseMultiplier(stance, &plain); got != multiplier {
			t.Errorf("%q: %v against %v", stance, got, multiplier)
		}
	}
	if got := defenseMultiplier(battle.StanceDefend, &shielded); got !=
		formula.ShieldMultiplier*formula.DefendMultiplier {
		t.Errorf("a defender that carries a shield pays both cuts: %v", got)
	}
	if got := defenseMultiplier(battle.StanceDodge, &shielded); got != formula.NoDefenseMultiplier {
		t.Errorf("a shield answers no dodge: %v", got)
	}
}

func TestTheCounterWeaponNeedsTheReachAndTheEnergy(t *testing.T) {
	defender := fighter("d1", battle.FactionAlly, battle.Cell{0, 0})
	costly := beam()
	costly.Name, costly.ENCost = "costly", 200
	shells := beam()
	shells.Name, shells.MapWeapon = "shells", true
	near := rifle("saber", 1, 1)
	defender.Mech.Weapons = []battle.Weapon{costly, shells, beam(), near}
	b := board(defender, fighter("e1", battle.FactionEnemy, battle.Cell{2, 0}))

	attacker := b.Unit("e1").Footprint()
	first := counterWeapon(b.Unit("d1"), "", attacker)
	named := counterWeapon(b.Unit("d1"), "saber", attacker)
	unpaid := counterWeapon(b.Unit("d1"), "costly", attacker)

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
