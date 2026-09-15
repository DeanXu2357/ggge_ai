package system

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
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
			u := unit{UnitContent: &state.UnitContent{Faction: battle.FactionAlly},
				Value: &state.UnitValue{HP: 100, EN: one.en}}
			weapon := def.Weapon{Name: "beam rifle", ENCost: one.cost}

			if got := hasENFor(u, weapon); got != one.want {
				t.Fatalf("EN %d against the cost %d: %v, want %v",
					one.en, one.cost, got, one.want)
			}
		})
	}
}

func TestTheENOfAShotComesFromThePanelAndNotFromTheMech(t *testing.T) {
	u := unit{
		UnitContent: &state.UnitContent{Faction: battle.FactionAlly, Mech: &def.Mech{EN: 200}},
		Value:       &state.UnitValue{HP: 100, EN: 10}}
	weapon := def.Weapon{Name: "beam rifle", ENCost: 20}

	if hasENFor(u, weapon) {
		t.Fatal("the predicate read the base data of the mech")
	}

	u.Value.EN = 20
	if !hasENFor(u, weapon) {
		t.Fatal("the predicate did not read the final panel")
	}
}

func TestAWeaponOfNoCategoryReadsTheHighestPilotValue(t *testing.T) {
	pilot := &def.Pilot{Ranged: 220, Melee: 180, Awaken: 240}
	melee := def.Weapon{Categories: []battle.WeaponCategory{battle.WeaponCategoryMelee}}
	both := def.Weapon{Categories: []battle.WeaponCategory{battle.WeaponCategoryMelee, battle.WeaponCategoryRanged}}

	if got := attackFor(pilot, def.Weapon{}); got != 240 {
		t.Fatalf("no category: %v", got)
	}
	if got := attackFor(pilot, melee); got != 180 {
		t.Fatalf("one category: %v", got)
	}
	if got := attackFor(pilot, both); got != 220 {
		t.Fatalf("two categories: %v", got)
	}
}
