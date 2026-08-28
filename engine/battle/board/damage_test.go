package board

import (
	"math"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var shot = battle.Weapon{Power: 1800}

func near(t *testing.T, name string, got, want float64) {
	t.Helper()
	if math.Abs(got-want) > 1e-9*math.Max(1, math.Abs(want)) {
		t.Fatalf("%s: %v against %v", name, got, want)
	}
}

func TestARatioHoldsAtZeroWhenTheAttackIsUnderTheDefense(t *testing.T) {
	if got := pilotRatio(100, battle.Pilot{Defense: 400}); got != 0 {
		t.Fatalf("pilot ratio: %v", got)
	}
	if got := mechRatio(battle.Mech{Attack: 1000}, battle.Mech{Defense: 5000}); got != 0 {
		t.Fatalf("mech ratio: %v", got)
	}
	near(t, "pilot ratio", pilotRatio(600, battle.Pilot{Defense: 100}), 0.1)
	near(t, "mech ratio", mechRatio(battle.Mech{Attack: 60000}, battle.Mech{Defense: 10000}), 1)
}

func TestASigmoidAtEqualValuesIsOneHalf(t *testing.T) {
	near(t, "pilot sigmoid", pilotSigmoid(220, battle.Pilot{Defense: 220}), 0.5)
	near(t, "mech sigmoid", mechSigmoid(battle.Mech{Attack: 4200}, battle.Mech{Defense: 4200}), 0.5)

	if pilotSigmoid(400, battle.Pilot{Defense: 100}) <= 0.5 ||
		mechSigmoid(battle.Mech{Attack: 5000}, battle.Mech{Defense: 1000}) <= 0.5 {
		t.Fatal("the stronger attacker must read above one half")
	}
	if pilotSigmoid(100, battle.Pilot{Defense: 400}) >= 0.5 ||
		mechSigmoid(battle.Mech{Attack: 1000}, battle.Mech{Defense: 5000}) >= 0.5 {
		t.Fatal("the weaker attacker must read under one half")
	}
}

func TestTerrainDividesTheCombatBaseDamage(t *testing.T) {
	attacker := &battle.Unit{Mech: battle.Mech{Attack: 4200}, Pilot: battle.Pilot{Ranged: 220}}
	defender := &battle.Unit{Mech: battle.Mech{Defense: 3900}, Pilot: battle.Pilot{Defense: 190}}

	plain := CombatBaseDamage(shot, attacker, defender, 1)
	rough := CombatBaseDamage(shot, attacker, defender, 2)

	if plain <= 0 {
		t.Fatalf("combat base damage: %v", plain)
	}
	near(t, "terrain 2", rough, plain/2)
	if plain <= BaseDamage(shot, attacker, defender) {
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
	near(t, "a shield that defends", FinalDamage(1000, 1, ShieldMultiplier*DefendMultiplier), 640)

	near(t, "a normal critical", CriticalDamage(1000, 1, NoDefenseMultiplier, CritNormal), 1100)
	near(t, "a high morale critical", CriticalDamage(1000, 1, DefendMultiplier, CritHighMorale), 960)
	near(t, "a super critical", CriticalDamage(1000, 1, ShieldMultiplier*DefendMultiplier, CritSuper), 832)
}

func TestTheExpectedDamageIsTheThreeFormulasInOrder(t *testing.T) {
	attacker := &battle.Unit{Mech: battle.Mech{Attack: 4200}, Pilot: battle.Pilot{Ranged: 220}}
	defender := &battle.Unit{Mech: battle.Mech{Defense: 3900}, Pilot: battle.Pilot{Defense: 190}}

	got := ExpectedDamage(shot, attacker, defender, 1.2, 0.35, 0.1, DefendMultiplier)

	want := FinalDamage(CombatBaseDamage(shot, attacker, defender, 1.2),
		DamageScale(0.35, 0.1), DefendMultiplier)
	near(t, "expected damage", got, want)
}
