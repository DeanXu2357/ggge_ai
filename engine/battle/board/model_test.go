package board

import "testing"

func TestAUnitHoldsTheENOfAWeaponWhenItCoversTheCost(t *testing.T) {
	cases := []struct {
		name string
		en   int
		cost int
		want bool
	}{
		{name: "the energy stands above the cost", en: 30, cost: 20, want: true},
		{name: "the energy equals the cost", en: 20, cost: 20, want: true},
		{name: "the energy falls one under the cost", en: 19, cost: 20, want: false},
		{name: "the unit holds no energy", en: 0, cost: 20, want: false},
		{name: "a weapon of no cost against no energy", en: 0, cost: 0, want: true},
	}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			unit := &unit{ID: "a1", Faction: factionAlly, HP: 100, EN: one.en}
			weapon := weapon{Name: "beam rifle", ENCost: one.cost}

			if got := unit.hasENFor(weapon); got != one.want {
				t.Fatalf("EN %d against the cost %d: %v, want %v",
					one.en, one.cost, got, one.want)
			}
		})
	}
}

func TestTheENOfAShotComesFromThePanelAndNotFromTheMech(t *testing.T) {
	unit := &unit{ID: "a1", Faction: factionAlly, HP: 100, EN: 10,
		Mech: mech{EN: 200}}
	weapon := weapon{Name: "beam rifle", ENCost: 20}

	if unit.hasENFor(weapon) {
		t.Fatal("the predicate read the base data of the mech")
	}

	unit.EN = 20
	if !unit.hasENFor(weapon) {
		t.Fatal("the predicate did not read the final panel")
	}
}

func TestAWeaponOfNoCategoryReadsTheHighestPilotValue(t *testing.T) {
	pilot := pilot{Ranged: 220, Melee: 180, Awaken: 240}
	melee := weapon{Categories: []weaponCategory{weaponCategoryMelee}}
	both := weapon{Categories: []weaponCategory{weaponCategoryMelee, weaponCategoryRanged}}

	if got := pilot.attackFor(weapon{}); got != 240 {
		t.Fatalf("no category: %v", got)
	}
	if got := pilot.attackFor(melee); got != 180 {
		t.Fatalf("one category: %v", got)
	}
	if got := pilot.attackFor(both); got != 220 {
		t.Fatalf("two categories: %v", got)
	}
}
