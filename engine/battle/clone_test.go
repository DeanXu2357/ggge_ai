package battle

import "testing"

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	board, err := NewBoard(Bounds{High: Cell{4, 4}}, []Unit{{
		ID: "a1", Faction: FactionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
		Weapons: []Weapon{{Name: "w"}},
		Ammo:    map[string]int{"w": 3},
		Debuffs: []Debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
		Mech:    Mech{Weapons: []Weapon{{Name: "base"}}},
	}})
	if err != nil {
		t.Fatal(err)
	}
	board.TerrainCells = map[Cell]Terrain{{1, 1}: TerrainGround}
	board.Phase = FactionAlly

	clone := board.Clone()
	clone.Units[0].HP = 1
	clone.Units[0].Weapons[0].Name = "changed"
	clone.Units[0].Ammo["w"] = 0
	clone.Units[0].Debuffs[0].Kind = "changed"
	clone.Units[0].Mech.Weapons[0].Name = "changed"
	clone.TerrainCells[Cell{1, 1}] = TerrainSpace
	clone.Phase = FactionEnemy

	unit := board.Units[0]
	if unit.HP != 10 || unit.Weapons[0].Name != "w" || unit.Ammo["w"] != 3 ||
		unit.Debuffs[0].Kind != "defense" || unit.Mech.Weapons[0].Name != "base" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if board.TerrainCells[Cell{1, 1}] != TerrainGround || board.Phase != FactionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}
