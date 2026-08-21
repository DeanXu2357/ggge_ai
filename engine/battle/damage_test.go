package battle

import (
	"math"
	"testing"
)

func near(t *testing.T, name string, got, want float64) {
	t.Helper()
	if math.Abs(got-want) > 1e-9*math.Max(1, math.Abs(want)) {
		t.Fatalf("%s: %v against %v", name, got, want)
	}
}

func TestARatioHoldsAtZeroWhenTheAttackIsUnderTheDefense(t *testing.T) {
	if got := pilotRatio(100, 400); got != 0 {
		t.Fatalf("pilot ratio: %v", got)
	}
	if got := unitRatio(1000, 5000); got != 0 {
		t.Fatalf("unit ratio: %v", got)
	}
	near(t, "pilot ratio", pilotRatio(600, 100), 0.1)
	near(t, "unit ratio", unitRatio(60000, 10000), 1)
}

func TestASigmoidAtEqualValuesIsOneHalf(t *testing.T) {
	near(t, "pilot sigmoid", pilotSigmoid(220, 220), 0.5)
	near(t, "unit sigmoid", unitSigmoid(4200, 4200), 0.5)

	if pilotSigmoid(400, 100) <= 0.5 || unitSigmoid(5000, 1000) <= 0.5 {
		t.Fatal("the stronger attacker must read above one half")
	}
	if pilotSigmoid(100, 400) >= 0.5 || unitSigmoid(1000, 5000) >= 0.5 {
		t.Fatal("the weaker attacker must read under one half")
	}
}

func TestTerrainDividesTheCombatBaseDamage(t *testing.T) {
	attacker := &Unit{UnitAttack: 4200, PilotAttack: 220}
	defender := &Unit{UnitDefense: 3900, PilotDefense: 190}

	plain := CombatBaseDamage(1800, attacker, defender, 1)
	rough := CombatBaseDamage(1800, attacker, defender, 2)

	if plain <= 0 {
		t.Fatalf("combat base damage: %v", plain)
	}
	near(t, "terrain 2", rough, plain/2)
	if plain <= BaseDamage(1800, attacker, defender) {
		t.Fatal("the attack correction outweighs the defense correction at these values")
	}
}

func TestTheDamageScaleAddsTheBonusAndDropsThePenalty(t *testing.T) {
	near(t, "no option", DamageScale(0, 0), 1)
	near(t, "both sides", DamageScale(0.5, 0.25), 1.25)
	near(t, "a full penalty", DamageScale(0, 1), 0)
	near(t, "over one penalty", DamageScale(0.25, 1.5), -0.25)
}

func TestTheDefenseAndTheCriticalMultiplyTheDamage(t *testing.T) {
	near(t, "no defense", FinalDamage(1000, 1, NoDefenseMultiplier), 1000)
	near(t, "a defense that the scale pays back", FinalDamage(1000, 1.25, DefendMultiplier), 1000)
	near(t, "a shield", FinalDamage(1000, 1, ShieldMultiplier), 600)

	near(t, "a normal critical", CriticalDamage(1000, 1, NoDefenseMultiplier, CritNormal), 1100)
	near(t, "a high morale critical", CriticalDamage(1000, 1, DefendMultiplier, CritHighMorale), 960)
	near(t, "a super critical", CriticalDamage(1000, 1, ShieldMultiplier, CritSuper), 780)
}

func TestTheExpectedDamageIsTheThreeFormulasInOrder(t *testing.T) {
	attacker := &Unit{UnitAttack: 4200, PilotAttack: 220}
	defender := &Unit{UnitDefense: 3900, PilotDefense: 190}

	got := ExpectedDamage(1800, attacker, defender, 1.2, 0.35, 0.1, DefendMultiplier)

	want := FinalDamage(CombatBaseDamage(1800, attacker, defender, 1.2),
		DamageScale(0.35, 0.1), DefendMultiplier)
	near(t, "expected damage", got, want)
}
