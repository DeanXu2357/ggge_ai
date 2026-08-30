package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func rifle(name string, rangeMin, rangeMax int) battle.Weapon {
	return battle.Weapon{Name: name, RangeMin: rangeMin, RangeMax: rangeMax, UsableAfterMove: true}
}

func actionsOf(t *testing.T, b *Board, id string) battle.ActionsResponse {
	t.Helper()
	out, err := b.Actions(id)
	if err != nil {
		t.Fatalf("actions: %v", err)
	}
	return out
}

func TestTheActionsCarryTheCellsTheUnitReaches(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{1, 0}))
	b.state.Units[0].Mech.MoveRange = 1

	out := actionsOf(t, b, "a1")

	want := []battle.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(out.MoveCells, want) {
		t.Fatalf("the foe blocks the cell (1,0): %v", out.MoveCells)
	}
	if out.Unit.UnitID != "a1" {
		t.Fatalf("unit: %v", out.Unit)
	}
}

// The command reads no resource and no band: a weapon with no energy left, a
// weapon that reaches nothing and a skill with no room all stay in the answer.
func TestTheActionsJudgeNoResourceAndNoBand(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{4, 4}))
	costly := rifle("costly", 1, 1)
	costly.ENCost = 20
	b.state.Units[0].EN = 0
	b.state.Units[0].Mech.Weapons = []battle.Weapon{costly}
	b.state.Units[0].MaxHP = b.state.Units[0].HP
	b.state.Units[0].Skills = []battle.Skill{{Kind: "skill_heal", Uses: 1}}

	out := actionsOf(t, b, "a1")

	if len(out.Weapons) != 1 || len(out.Skills) != 1 {
		t.Fatalf("the answer holds the whole panel: %+v", out)
	}
}

func TestTheActionsOfAUnitThatCannotAnswerAreAnError(t *testing.T) {
	b := board(unitAt("a1", battle.FactionAlly, battle.Cell{0, 0}),
		unitAt("e1", battle.FactionEnemy, battle.Cell{2, 0}))
	dead := unitAt("a2", battle.FactionAlly, battle.Cell{0, 1})
	dead.HP = 0
	b.state.Units = append(b.state.Units, dead)
	cases := map[string]struct {
		unitID string
		want   error
	}{
		"an unknown unit":      {"ghost", battle.ErrNoUnit},
		"a destroyed unit":     {"a2", battle.ErrDestroyed},
		"a unit off the phase": {"e1", battle.ErrOffPhase},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := b.Actions(one.unitID)

			if !errors.Is(err, one.want) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	amount := 0.5
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	b := &Board{state: battle.BattleState{Bounds: &bounds, Units: []battle.Unit{{
		ID: "a1", Faction: battle.FactionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
		Ammo:    map[string]int{"w": 3},
		Debuffs: []battle.Debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
		Skills:  []battle.Skill{{Kind: "boost", Amount: &amount, Uses: 1}},
		Mech:    battle.Mech{Weapons: []battle.Weapon{{Name: "w"}}},
	}}}}
	b.state.TerrainCells = []battle.TerrainCell{{Cell: battle.Cell{1, 1}, Terrain: battle.TerrainGround}}
	b.state.Phase = battle.FactionAlly

	clone := b.Clone().(*Board)
	clone.state.Units[0].HP = 1
	clone.state.Units[0].Ammo["w"] = 0
	clone.state.Units[0].Debuffs[0].Kind = "changed"
	*clone.state.Units[0].Skills[0].Amount = 9
	clone.state.Units[0].Skills[0].Uses = 2
	clone.state.TerrainCells[0].Terrain = battle.TerrainSpace
	clone.state.Phase = battle.FactionEnemy

	unit := b.state.Units[0]
	if unit.HP != 10 || unit.Ammo["w"] != 3 || unit.Debuffs[0].Kind != "defense" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if *unit.Skills[0].Amount != 0.5 || unit.Skills[0].Uses != 1 {
		t.Fatalf("the board skill changed with the clone: %+v", unit.Skills[0])
	}
	if b.state.TerrainCells[0].Terrain != battle.TerrainGround || b.state.Phase != battle.FactionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}
