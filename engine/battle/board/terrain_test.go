package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func TestACellTakesTheTerrainOfTheBoardOrItsOwn(t *testing.T) {
	state := &Board{
		bounds:         battle.Bounds{Low: battle.Cell{0, 0}, High: battle.Cell{4, 4}},
		defaultTerrain: battle.TerrainGround,
		terrainCells:   map[battle.Cell]battle.Terrain{{2, 2}: battle.TerrainUnderwater},
	}

	if got := state.TerrainAt(battle.Cell{0, 0}); got != battle.TerrainGround {
		t.Fatalf("a cell with no override: %v", got)
	}
	if got := state.TerrainAt(battle.Cell{2, 2}); got != battle.TerrainUnderwater {
		t.Fatalf("a cell with an override: %v", got)
	}
}

func TestAUnitStandsOnTheTerrainOfItsAnchorCell(t *testing.T) {
	state := &Board{
		bounds:         battle.Bounds{Low: battle.Cell{0, 0}, High: battle.Cell{4, 4}},
		defaultTerrain: battle.TerrainSurface,
		terrainCells:   map[battle.Cell]battle.Terrain{{1, 1}: battle.TerrainUnderwater, {2, 1}: battle.TerrainGround},
		units: []battle.Unit{
			{ID: "a1", Faction: battle.FactionAlly, HP: 1,
				Footprint: battle.Footprint{Anchor: battle.Cell{1, 1}, Size: battle.Size{2, 2}}},
			{ID: "e1", Faction: battle.FactionEnemy, HP: 1,
				Footprint: battle.Footprint{Anchor: battle.Cell{3, 3}, Size: battle.Size{1, 1}}},
		},
	}

	if got := state.TerrainOf(state.Unit("a1")); got != battle.TerrainUnderwater {
		t.Fatalf("the anchor cell holds the terrain of the unit: %v", got)
	}
	if got := state.TerrainOf(state.Unit("e1")); got != battle.TerrainSurface {
		t.Fatalf("a unit off every override: %v", got)
	}
}

func TestABoardWithNoTerrainReadsSpace(t *testing.T) {
	state, err := New(battle.Bounds{Low: battle.Cell{0, 0}, High: battle.Cell{4, 4}}, nil)
	if err != nil {
		t.Fatalf("board: %v", err)
	}

	if got := state.TerrainAt(battle.Cell{3, 1}); got != battle.TerrainSpace {
		t.Fatalf("the zero value of the board: %v", got)
	}
}

func TestAPayloadWithNoTerrainDecodesToNoRestriction(t *testing.T) {
	state, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if state.defaultTerrain != battle.TerrainSpace || state.terrainCells != nil {
		t.Fatalf("board: %v %v", state.defaultTerrain, state.terrainCells)
	}
}

func TestTheDecodeRefusesATerrainOutsideTheContract(t *testing.T) {
	cases := map[string]func(*protocol.BattleState){
		"the map": func(state *protocol.BattleState) { state.Terrain = "orbit" },
		"a cell": func(state *protocol.BattleState) {
			state.TerrainCells = []protocol.TerrainCell{{Cell: protocol.Cell{1, 1}, Terrain: "lava"}}
		},
	}

	for name, spoil := range cases {
		t.Run(name, func(t *testing.T) {
			state := wireBoard()
			spoil(state)

			if _, err := DecodeState(state); err == nil {
				t.Fatal("the decode took a terrain outside the contract")
			}
		})
	}
}
