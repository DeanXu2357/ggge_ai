package battle

import "testing"

func fighter(id string, faction Faction, anchor Cell) Unit {
	out := unit(id, faction, anchor)
	out.HP, out.MaxHP = 12000, 12000
	out.EN, out.ENMax = 140, 140
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Attack, out.Pilot.Defense = 220, 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func beam() Weapon {
	out := rifle("beam rifle", RadiusRange{Min: 1, Max: 3})
	out.Power, out.Accuracy, out.ENCost = 1800, 5, 10
	return out
}

func TestTheDamageOfOneShotReadsTheStanceAndTheDebuffs(t *testing.T) {
	attacker := fighter("a1", FactionAlly, Cell{0, 0})
	defender := fighter("e1", FactionEnemy, Cell{2, 0})
	weapon := beam()
	rules := DefaultRules()

	plain := StrikeDamage(&attacker, &defender, &weapon, NoDefenseMultiplier)
	defended := StrikeDamage(&attacker, &defender, &weapon, rules.DefendMultiplier)
	defender.Debuffs = []Debuff{{Kind: "armor_break", Magnitude: 0.2}}
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
	scale := CombatBaseDamage(1, &blank, &blank, NoTerrainCorrection)
	low := Weapon{Power: 2.5 / scale}
	high := Weapon{Power: 3.5 / scale}

	raw := ExpectedDamage(low.Power, &blank, &blank, NoTerrainCorrection, 0, 0, NoDefenseMultiplier)
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
	attacker := fighter("a1", FactionAlly, Cell{0, 0})
	defender := fighter("e1", FactionEnemy, Cell{2, 0})
	weapon := beam()
	rules := DefaultRules()

	plain := StrikeHitProbability(&attacker, &defender, &weapon, false, rules)
	dodged := StrikeHitProbability(&attacker, &defender, &weapon, true, rules)

	if plain != HitProbability(weapon, &attacker, &defender, 0) {
		t.Fatalf("a shot that meets no dodge carries no correction: %v", plain)
	}
	if dodged != HitProbability(weapon, &attacker, &defender, -rules.DodgeHitPenalty) {
		t.Fatalf("a dodge takes the penalty of the rules off the rate: %v", dodged)
	}
}

func TestTheStanceMultiplierOfEveryStance(t *testing.T) {
	rules := DefaultRules()
	plain := fighter("d1", FactionAlly, Cell{0, 0})
	shielded := fighter("d2", FactionAlly, Cell{0, 1})
	shielded.HasShield = true

	want := map[Stance]float64{
		StanceDefend:  rules.DefendMultiplier,
		StanceDodge:   NoDefenseMultiplier,
		StanceCounter: NoDefenseMultiplier,
		StanceNone:    NoDefenseMultiplier,
	}
	for stance, multiplier := range want {
		if got := rules.StanceMultiplier(stance, &plain); got != multiplier {
			t.Errorf("%q: %v against %v", stance, got, multiplier)
		}
	}
	if got := rules.StanceMultiplier(StanceDefend, &shielded); got != rules.ShieldMultiplier {
		t.Errorf("a defender that carries a shield defends with it: %v", got)
	}
	if got := rules.StanceMultiplier(StanceDodge, &shielded); got != NoDefenseMultiplier {
		t.Errorf("a shield answers no dodge: %v", got)
	}
}

func TestAnInterceptorTakesTheStrikeInADefenseState(t *testing.T) {
	rules := DefaultRules()
	plain := fighter("h1", FactionAlly, Cell{0, 0})
	shielded := fighter("h2", FactionAlly, Cell{0, 1})
	shielded.HasShield = true
	tough := fighter("h3", FactionAlly, Cell{0, 2})
	tough.InterceptionReduction = 0.25

	if got := rules.InterceptionMultiplier(&plain); got != rules.SupportDefendMultiplier {
		t.Errorf("interceptor: %v", got)
	}
	if got := rules.InterceptionMultiplier(&shielded); got != rules.ShieldMultiplier {
		t.Errorf("a shield holder intercepts in a shield state: %v", got)
	}
	if got := rules.InterceptionMultiplier(&tough); got != rules.SupportDefendMultiplier*0.75 {
		t.Errorf("the reduction of the unit rides on the state: %v", got)
	}
}

func TestTheCounterWeaponNeedsTheReachTheEnergyAndThePermission(t *testing.T) {
	defender := fighter("d1", FactionAlly, Cell{0, 0})
	costly := beam()
	costly.Name, costly.ENCost = "costly", 200
	passive := beam()
	passive.Name, passive.CanCounter = "net", false
	shells := beam()
	shells.Name, shells.MapWeapon = "shells", true
	near := rifle("saber", RadiusRange{Min: 1, Max: 1})
	defender.Weapons = []Weapon{costly, passive, shells, beam(), near}
	state := board(defender, fighter("e1", FactionEnemy, Cell{2, 0}))

	attacker := state.Unit("e1").Footprint
	first := state.CounterWeapon(state.Unit("d1"), "", attacker)
	named := state.CounterWeapon(state.Unit("d1"), "saber", attacker)
	unpaid := state.CounterWeapon(state.Unit("d1"), "costly", attacker)

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
	dice := Forced{AttackerSupport: true, Strike: false, Counter: true}

	if !dice.Lands(NodeAttackerSupport, 0) || dice.Lands(NodeStrike, 1) ||
		!dice.Lands(NodeCounter, 0.5) {
		t.Fatal("each node reads its own outcome, and no node reads the probability")
	}
}
