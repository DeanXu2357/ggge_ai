package state

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

func TestACloneSharesTheDefinitionsAndCopiesTheState(t *testing.T) {
	amount := 0.5
	mech := &def.Mech{Weapons: []def.Weapon{{Name: "w"}}}
	pilot := &def.Pilot{Ranged: 220}
	board := Board{
		Bounds: Bounds{High: Cell{4, 4}},
		Units: []Unit{{
			ID: "a1", Faction: FactionAlly, HP: 10, Mech: mech, Pilot: pilot,
			Ammo:    map[string]int{"w": 3},
			Debuffs: []Debuff{{Kind: "defense", Magnitude: 0.1}},
			Skills:  []Skill{{Kind: "boost", Amount: &amount}},
		}},
	}

	clone := board.Clone()

	if clone.Units[0].Mech != mech || clone.Units[0].Pilot != pilot {
		t.Fatal("the clone reads the definitions of the board itself")
	}
	clone.Units[0].Debuffs[0].Kind = "changed"
	clone.Units[0].Ammo["w"] = 0
	*clone.Units[0].Skills[0].Amount = 9
	unit := board.Units[0]
	if unit.Debuffs[0].Kind != "defense" || unit.Ammo["w"] != 3 ||
		*unit.Skills[0].Amount != 0.5 {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
}
