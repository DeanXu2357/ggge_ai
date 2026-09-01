package battle

import (
	"testing"
)

func TestACloneSharesTheWeaponsAndCopiesTheState(t *testing.T) {
	amount := 0.5
	bounds := Bounds{{0, 0}, {4, 4}}
	state := BattleState{
		Bounds: &bounds,
		Units: []Unit{{
			ID: "a1", Faction: FactionAlly, HP: 10,
			Mech:    Mech{Weapons: []Weapon{{Name: "w"}}},
			Pilot:   Pilot{Ranged: 220},
			Ammo:    map[string]int{"w": 3},
			Debuffs: []Debuff{{Kind: "defense", Magnitude: 0.1}},
			Skills:  []Skill{{Kind: "boost", Amount: &amount}},
		}},
	}

	clone := state.Clone()

	if &clone.Units[0].Mech.Weapons[0] != &state.Units[0].Mech.Weapons[0] {
		t.Fatal("the clone reads the weapons of the state itself")
	}
	clone.Units[0].HP = 1
	clone.Units[0].Pilot.Ranged = 0
	clone.Units[0].Debuffs[0].Kind = "changed"
	clone.Units[0].Ammo["w"] = 0
	*clone.Units[0].Skills[0].Amount = 9
	clone.Bounds[1] = Cell{9, 9}

	unit := state.Units[0]
	if unit.HP != 10 || unit.Pilot.Ranged != 220 || unit.Debuffs[0].Kind != "defense" ||
		unit.Ammo["w"] != 3 || *unit.Skills[0].Amount != 0.5 {
		t.Fatalf("the state changed with its clone: %+v", unit)
	}
	if *state.Bounds != (Bounds{{0, 0}, {4, 4}}) {
		t.Fatalf("the bounds changed with the clone: %v", *state.Bounds)
	}
}
