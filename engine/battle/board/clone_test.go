package board

import (
	"testing"
)

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	amount := 0.5
	state, err := newBoard(bounds{High: cell{4, 4}}, []unit{{
		ID: "a1", Faction: factionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
		Ammo:    map[string]int{"w": 3},
		Debuffs: []debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
		Skills:  []skill{{Kind: "boost", Amount: &amount, Uses: 1}},
		Mech:    mech{Weapons: []weapon{{Name: "w"}}},
	}})
	if err != nil {
		t.Fatal(err)
	}
	state.terrainCells = map[cell]terrain{{1, 1}: terrainGround}
	state.phase = factionAlly

	clone := state.Clone().(*Board)
	clone.units[0].HP = 1
	clone.units[0].Mech.Weapons[0].Name = "changed"
	clone.units[0].Ammo["w"] = 0
	clone.units[0].Debuffs[0].Kind = "changed"
	*clone.units[0].Skills[0].Amount = 9
	clone.units[0].Skills[0].Uses = 2
	clone.terrainCells[cell{1, 1}] = terrainSpace
	clone.phase = factionEnemy

	unit := state.units[0]
	if unit.HP != 10 || unit.Mech.Weapons[0].Name != "w" || unit.Ammo["w"] != 3 ||
		unit.Debuffs[0].Kind != "defense" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if *unit.Skills[0].Amount != 0.5 || unit.Skills[0].Uses != 1 {
		t.Fatalf("the board skill changed with the clone: %+v", unit.Skills[0])
	}
	if state.terrainCells[cell{1, 1}] != terrainGround || state.phase != factionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}
