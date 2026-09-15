package system

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func wireDuel() battle.BattleState {
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	unit := func(faction battle.Faction, x int) battle.Unit {
		return battle.Unit{Faction: faction, Pos: battle.Cell{x, 0}, HP: 100, MaxHP: 100, EN: 10, ENMax: 10}
	}
	return battle.BattleState{Bounds: &bounds, Phase: battle.FactionAlly, Turn: 1,
		Units: []battle.Unit{unit(battle.FactionAlly, 0), unit(battle.FactionEnemy, 3)}}
}

// A maximum of zero is a broken payload, not a value to fill.
func TestAssembleRefusesAUnitWhoseMaximumIsZero(t *testing.T) {
	for name, edit := range map[string]func(u *battle.Unit){
		"max HP": func(u *battle.Unit) { u.MaxHP = 0 },
		"max EN": func(u *battle.Unit) { u.ENMax = 0 },
	} {
		t.Run(name, func(t *testing.T) {
			candidate := wireDuel()
			edit(&candidate.Units[1])

			_, _, err := Assemble(candidate)

			require.Error(t, err)
			assert.Contains(t, err.Error(), "unit 1")
		})
	}
}

func TestAssembleAnswersTheTwoColumnsOfAValidState(t *testing.T) {
	content, values, err := Assemble(wireDuel())

	require.NoError(t, err)
	assert.Len(t, content.Units, 2)
	assert.Len(t, values.Units, 2)
	assert.Equal(t, battle.TerrainSpace, content.Terrain, "an empty terrain becomes space")
	assert.Equal(t, battle.Cell{1, 1}, content.Units[0].Size, "a size of zero becomes one")
}
