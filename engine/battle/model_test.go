package battle

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
			unit := &Unit{ID: "a1", Faction: FactionAlly, HP: 100, EN: one.en}
			weapon := Weapon{Name: "beam rifle", ENCost: one.cost}

			if got := unit.HasENFor(weapon); got != one.want {
				t.Fatalf("EN %d against the cost %d: %v, want %v",
					one.en, one.cost, got, one.want)
			}
		})
	}
}

func TestTheENOfAShotComesFromThePanelAndNotFromTheMech(t *testing.T) {
	unit := &Unit{ID: "a1", Faction: FactionAlly, HP: 100, EN: 10,
		Mech: Mech{EN: 200}}
	weapon := Weapon{Name: "beam rifle", ENCost: 20}

	if unit.HasENFor(weapon) {
		t.Fatal("the predicate read the base data of the mech")
	}

	unit.EN = 20
	if !unit.HasENFor(weapon) {
		t.Fatal("the predicate did not read the final panel")
	}
}

func TestAWeaponOfNoCategoryReadsTheHighestPilotValue(t *testing.T) {
	pilot := Pilot{Ranged: 220, Melee: 180, Awaken: 240}
	melee := Weapon{Categories: []WeaponCategory{WeaponCategoryMelee}}
	both := Weapon{Categories: []WeaponCategory{WeaponCategoryMelee, WeaponCategoryRanged}}

	if got := pilot.AttackFor(Weapon{}); got != 240 {
		t.Fatalf("no category: %v", got)
	}
	if got := pilot.AttackFor(melee); got != 180 {
		t.Fatalf("one category: %v", got)
	}
	if got := pilot.AttackFor(both); got != 220 {
		t.Fatalf("two categories: %v", got)
	}
}
