package board

import (
	"testing"
)

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	amount := 0.5
	state, err := New(Bounds{High: Cell{4, 4}}, []Unit{{
		ID: "a1", Faction: FactionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
		Ammo:    map[string]int{"w": 3},
		Debuffs: []Debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
		Skills:  []Skill{{Kind: "boost", Amount: &amount, Uses: 1}},
		Mech:    Mech{Weapons: []Weapon{{Name: "w"}}},
	}})
	if err != nil {
		t.Fatal(err)
	}
	state.terrainCells = map[Cell]Terrain{{1, 1}: TerrainGround}
	state.phase = FactionAlly

	clone := state.Clone().(*Board)
	clone.units[0].HP = 1
	clone.units[0].Mech.Weapons[0].Name = "changed"
	clone.units[0].Ammo["w"] = 0
	clone.units[0].Debuffs[0].Kind = "changed"
	*clone.units[0].Skills[0].Amount = 9
	clone.units[0].Skills[0].Uses = 2
	clone.terrainCells[Cell{1, 1}] = TerrainSpace
	clone.phase = FactionEnemy

	unit := state.units[0]
	if unit.HP != 10 || unit.Mech.Weapons[0].Name != "w" || unit.Ammo["w"] != 3 ||
		unit.Debuffs[0].Kind != "defense" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if *unit.Skills[0].Amount != 0.5 || unit.Skills[0].Uses != 1 {
		t.Fatalf("the board skill changed with the clone: %+v", unit.Skills[0])
	}
	if state.terrainCells[Cell{1, 1}] != TerrainGround || state.phase != FactionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}
