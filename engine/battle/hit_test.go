package battle

import "testing"

func TestTheHitRateHoldsBetweenZeroAndOneHundred(t *testing.T) {
	weapon := Weapon{Accuracy: 96.45}
	quick := &Unit{Pilot: Pilot{Attack: 400}, Mech: Mech{Mobility: 1000}}
	still := &Unit{}
	evasive := &Unit{Pilot: Pilot{Reaction: 3000}, Mech: Mech{Mobility: 500}}

	if got := HitRatePercent(weapon, quick, still, 0); got != 100 {
		t.Fatalf("a rate over one hundred: %v", got)
	}
	if got := HitRatePercent(weapon, still, evasive, 0); got != 0 {
		t.Fatalf("a rate under zero: %v", got)
	}
	near(t, "no correction", HitRatePercent(weapon, still, still, 0), weapon.Accuracy)
	near(t, "an ability correction", HitRatePercent(weapon, still, still, -20),
		weapon.Accuracy-20)
}

func TestTheHitRateFollowsTheAccuracyOfTheWeapon(t *testing.T) {
	still := &Unit{}
	// A reaction of 500 costs twenty points, so the accuracy of 105 stays under
	// the clamp and the two rates keep their full distance.
	reactive := &Unit{Pilot: Pilot{Reaction: 500}}
	sloppy := Weapon{Accuracy: 90}
	precise := Weapon{Accuracy: 105}

	near(t, "the accuracy alone", HitRatePercent(sloppy, still, still, 0), 90)
	near(t, "the span of the game values",
		HitRatePercent(precise, still, reactive, 0)-HitRatePercent(sloppy, still, reactive, 0), 15)
}

func TestAWeaponWithNoAccuracyCarriesNoBase(t *testing.T) {
	attacker := &Unit{Mech: Mech{Mobility: 500}}
	still := &Unit{}

	near(t, "the mobility term alone", HitRatePercent(Weapon{}, attacker, still, 0), 3.66)
}

func TestTheMobilityOfEachSideMovesTheHitRateItsOwnWay(t *testing.T) {
	weapon := Weapon{Accuracy: 95}
	still := &Unit{}
	attacker := &Unit{Mech: Mech{Mobility: 500}}
	defender := &Unit{Mech: Mech{Mobility: 500}}

	if HitRatePercent(weapon, attacker, still, 0) <= HitRatePercent(weapon, still, still, 0) {
		t.Fatal("the mobility of the attacker raises the rate")
	}
	if HitRatePercent(weapon, still, defender, 0) >= HitRatePercent(weapon, still, still, 0) {
		t.Fatal("the mobility of the defender lowers the rate")
	}
}

func TestTheHitProbabilityIsTheRateOverOneHundred(t *testing.T) {
	weapon := Weapon{Accuracy: 90}
	attacker := &Unit{Pilot: Pilot{Attack: 220}, Mech: Mech{Mobility: 310}}
	defender := &Unit{Pilot: Pilot{Reaction: 205}, Mech: Mech{Mobility: 310}}

	got := HitProbability(weapon, attacker, defender, 0)

	if got != HitRatePercent(weapon, attacker, defender, 0)/100 {
		t.Fatalf("probability: %v", got)
	}
	if got <= 0 || got >= 1 {
		t.Fatalf("probability: %v", got)
	}
}
