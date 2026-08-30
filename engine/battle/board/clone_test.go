package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	amount := 0.5
	b, err := newBoard(state.Bounds{High: state.Cell{4, 4}}, []state.Unit{{
		ID: "a1", Faction: state.FactionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
		Ammo:    map[string]int{"w": 3},
		Debuffs: []state.Debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
		Skills:  []state.Skill{{Kind: "boost", Amount: &amount, Uses: 1}},
		Mech:    &def.Mech{Weapons: []def.Weapon{{Name: "w"}}},
	}})
	if err != nil {
		t.Fatal(err)
	}
	b.state.TerrainCells = map[state.Cell]state.Terrain{{1, 1}: state.TerrainGround}
	b.state.Phase = state.FactionAlly

	clone := b.Clone().(*Board)
	clone.state.Units[0].HP = 1
	clone.state.Units[0].Ammo["w"] = 0
	clone.state.Units[0].Debuffs[0].Kind = "changed"
	*clone.state.Units[0].Skills[0].Amount = 9
	clone.state.Units[0].Skills[0].Uses = 2
	clone.state.TerrainCells[state.Cell{1, 1}] = state.TerrainSpace
	clone.state.Phase = state.FactionEnemy

	unit := b.state.Units[0]
	if unit.HP != 10 || unit.Ammo["w"] != 3 || unit.Debuffs[0].Kind != "defense" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if *unit.Skills[0].Amount != 0.5 || unit.Skills[0].Uses != 1 {
		t.Fatalf("the board skill changed with the clone: %+v", unit.Skills[0])
	}
	if b.state.TerrainCells[state.Cell{1, 1}] != state.TerrainGround || b.state.Phase != state.FactionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}
