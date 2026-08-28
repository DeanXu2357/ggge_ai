package formula

import (
	"testing"
)

func TestTheHitRateHoldsBetweenZeroAndOneHundred(t *testing.T) {
	accuracy := 96.45
	quick := Side{PilotAttack: 400, Mobility: 1000}
	still := Side{}
	evasive := Side{PilotReaction: 3000, Mobility: 500}

	if got := HitRatePercent(accuracy, quick, still, 0); got != 100 {
		t.Fatalf("a rate over one hundred: %v", got)
	}
	if got := HitRatePercent(accuracy, still, evasive, 0); got != 0 {
		t.Fatalf("a rate under zero: %v", got)
	}
	near(t, "no correction", HitRatePercent(accuracy, still, still, 0), accuracy)
	near(t, "an ability correction", HitRatePercent(accuracy, still, still, -20),
		accuracy-20)
}

func TestTheHitRateFollowsTheAccuracyOfTheWeapon(t *testing.T) {
	still := Side{}
	// A reaction of 500 costs twenty points, so the accuracy of 105 stays under
	// the clamp and the two rates keep their full distance.
	reactive := Side{PilotReaction: 500}
	sloppy := 90.0
	precise := 105.0

	near(t, "the accuracy alone", HitRatePercent(sloppy, still, still, 0), 90)
	near(t, "the span of the game values",
		HitRatePercent(precise, still, reactive, 0)-HitRatePercent(sloppy, still, reactive, 0), 15)
}

func TestAWeaponWithNoAccuracyCarriesNoBase(t *testing.T) {
	attacker := Side{Mobility: 500}
	still := Side{}

	near(t, "the mobility term alone", HitRatePercent(0, attacker, still, 0), 3.66)
}

func TestTheMobilityOfEachSideMovesTheHitRateItsOwnWay(t *testing.T) {
	accuracy := 95.0
	still := Side{}
	attacker := Side{Mobility: 500}
	defender := Side{Mobility: 500}

	if HitRatePercent(accuracy, attacker, still, 0) <= HitRatePercent(accuracy, still, still, 0) {
		t.Fatal("the mobility of the attacker raises the rate")
	}
	if HitRatePercent(accuracy, still, defender, 0) >= HitRatePercent(accuracy, still, still, 0) {
		t.Fatal("the mobility of the defender lowers the rate")
	}
}

func TestTheHitProbabilityIsTheRateOverOneHundred(t *testing.T) {
	accuracy := 90.0
	attacker := Side{PilotAttack: 220, Mobility: 310}
	defender := Side{PilotReaction: 205, Mobility: 310}

	got := HitProbability(accuracy, attacker, defender, 0)

	if got != HitRatePercent(accuracy, attacker, defender, 0)/100 {
		t.Fatalf("probability: %v", got)
	}
	if got <= 0 || got >= 1 {
		t.Fatalf("probability: %v", got)
	}
}
