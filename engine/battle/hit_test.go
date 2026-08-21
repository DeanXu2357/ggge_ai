package battle

import "testing"

func TestTheHitRateHoldsBetweenZeroAndOneHundred(t *testing.T) {
	quick := &Unit{Pilot: Pilot{Attack: 400}, Mech: Mech{Mobility: 1000}}
	still := &Unit{}
	evasive := &Unit{Pilot: Pilot{Reaction: 3000}, Mech: Mech{Mobility: 500}}

	if got := HitRatePercent(quick, still, 0); got != 100 {
		t.Fatalf("a rate over one hundred: %v", got)
	}
	if got := HitRatePercent(still, evasive, 0); got != 0 {
		t.Fatalf("a rate under zero: %v", got)
	}
	near(t, "no correction", HitRatePercent(still, still, 0), hitBase)
	near(t, "an ability correction", HitRatePercent(still, still, -20), hitBase-20)
}

func TestTheMobilityOfEachSideMovesTheHitRateItsOwnWay(t *testing.T) {
	still := &Unit{}
	attacker := &Unit{Mech: Mech{Mobility: 500}}
	defender := &Unit{Mech: Mech{Mobility: 500}}

	if HitRatePercent(attacker, still, 0) <= HitRatePercent(still, still, 0) {
		t.Fatal("the mobility of the attacker raises the rate")
	}
	if HitRatePercent(still, defender, 0) >= HitRatePercent(still, still, 0) {
		t.Fatal("the mobility of the defender lowers the rate")
	}
}

func TestTheHitProbabilityIsTheRateOverOneHundred(t *testing.T) {
	attacker := &Unit{Pilot: Pilot{Attack: 220}, Mech: Mech{Mobility: 310}}
	defender := &Unit{Pilot: Pilot{Reaction: 205}, Mech: Mech{Mobility: 310}}

	got := HitProbability(attacker, defender, 0)

	if got != HitRatePercent(attacker, defender, 0)/100 {
		t.Fatalf("probability: %v", got)
	}
	if got <= 0 || got >= 1 {
		t.Fatalf("probability: %v", got)
	}
}
