package engagement

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var oneCell = state.Size{1, 1}

func unitAt(id string, faction state.Faction, anchor state.Cell) state.Unit {
	return state.Unit{ID: id, Faction: faction,
		Footprint: state.Footprint{Anchor: anchor, Size: oneCell}, HP: 100,
		Mech: &def.Mech{}, Pilot: &def.Pilot{}}
}

func board(units ...state.Unit) *state.Board {
	return &state.Board{
		Bounds: state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{4, 4}}, Units: units,
		Phase: state.FactionAlly, Turn: 1}
}

func rifle(name string, band def.RadiusRange) def.Weapon {
	return def.Weapon{Name: name, Range: band, UsableAfterMove: true}
}

func fighter(id string, faction state.Faction, anchor state.Cell) state.Unit {
	out := unitAt(id, faction, anchor)
	out.HP, out.MaxHP = 12000, 12000
	out.EN, out.ENMax = 140, 140
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func beam() def.Weapon {
	out := rifle("beam rifle", def.RadiusRange{Min: 1, Max: 3})
	out.Power, out.Accuracy, out.ENCost = 1800, 5, 10
	return out
}

func TestTheDamageOfOneShotReadsTheStanceAndTheDebuffs(t *testing.T) {
	attacker := fighter("a1", state.FactionAlly, state.Cell{0, 0})
	defender := fighter("e1", state.FactionEnemy, state.Cell{2, 0})
	weapon := beam()

	plain := strikeDamage(&attacker, &defender, &weapon, formula.NoDefenseMultiplier)
	defended := strikeDamage(&attacker, &defender, &weapon, formula.DefendMultiplier)
	defender.Debuffs = []state.Debuff{{Kind: "armor_break", Magnitude: 0.2}}
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
	attacker := fighter("a1", state.FactionAlly, state.Cell{0, 0})
	defender := fighter("e1", state.FactionEnemy, state.Cell{2, 0})
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
	plain := fighter("d1", state.FactionAlly, state.Cell{0, 0})
	shielded := fighter("d2", state.FactionAlly, state.Cell{0, 1})
	shielded.HasShield = true

	want := map[Stance]float64{
		StanceDefend:  formula.DefendMultiplier,
		StanceDodge:   formula.NoDefenseMultiplier,
		StanceCounter: formula.NoDefenseMultiplier,
		StanceNone:    formula.NoDefenseMultiplier,
	}
	for stance, multiplier := range want {
		if got := defenseMultiplier(stance, &plain); got != multiplier {
			t.Errorf("%q: %v against %v", stance, got, multiplier)
		}
	}
	if got := defenseMultiplier(StanceDefend, &shielded); got !=
		formula.ShieldMultiplier*formula.DefendMultiplier {
		t.Errorf("a defender that carries a shield pays both cuts: %v", got)
	}
	if got := defenseMultiplier(StanceDodge, &shielded); got != formula.NoDefenseMultiplier {
		t.Errorf("a shield answers no dodge: %v", got)
	}
}

func TestTheCounterWeaponNeedsTheReachAndTheEnergy(t *testing.T) {
	defender := fighter("d1", state.FactionAlly, state.Cell{0, 0})
	costly := beam()
	costly.Name, costly.ENCost = "costly", 200
	shells := beam()
	shells.Name, shells.MapWeapon = "shells", true
	near := rifle("saber", def.RadiusRange{Min: 1, Max: 1})
	defender.Mech.Weapons = []def.Weapon{costly, shells, beam(), near}
	b := board(defender, fighter("e1", state.FactionEnemy, state.Cell{2, 0}))

	attacker := b.Unit("e1").Footprint
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
