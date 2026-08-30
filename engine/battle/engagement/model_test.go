package engagement

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

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
			unit := &battle.Unit{ID: "a1", Faction: battle.FactionAlly, HP: 100, EN: one.en}
			weapon := battle.Weapon{Name: "beam rifle", ENCost: one.cost}

			if got := hasENFor(unit, weapon); got != one.want {
				t.Fatalf("EN %d against the cost %d: %v, want %v",
					one.en, one.cost, got, one.want)
			}
		})
	}
}

func TestTheENOfAShotComesFromThePanelAndNotFromTheMech(t *testing.T) {
	unit := &battle.Unit{ID: "a1", Faction: battle.FactionAlly, HP: 100, EN: 10,
		Mech: battle.Mech{EN: 200}}
	weapon := battle.Weapon{Name: "beam rifle", ENCost: 20}

	if hasENFor(unit, weapon) {
		t.Fatal("the predicate read the base data of the mech")
	}

	unit.EN = 20
	if !hasENFor(unit, weapon) {
		t.Fatal("the predicate did not read the final panel")
	}
}

func TestAWeaponOfNoCategoryReadsTheHighestPilotValue(t *testing.T) {
	pilot := &battle.Pilot{Ranged: 220, Melee: 180, Awaken: 240}
	melee := battle.Weapon{Categories: []battle.WeaponCategory{battle.WeaponCategoryMelee}}
	both := battle.Weapon{Categories: []battle.WeaponCategory{battle.WeaponCategoryMelee, battle.WeaponCategoryRanged}}

	if got := attackFor(pilot, battle.Weapon{}); got != 240 {
		t.Fatalf("no category: %v", got)
	}
	if got := attackFor(pilot, melee); got != 180 {
		t.Fatalf("one category: %v", got)
	}
	if got := attackFor(pilot, both); got != 220 {
		t.Fatalf("two categories: %v", got)
	}
}
