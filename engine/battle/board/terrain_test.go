package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func TestACellTakesTheTerrainOfTheBoardOrItsOwn(t *testing.T) {
	state := &Board{
		bounds:         bounds{Low: cell{0, 0}, High: cell{4, 4}},
		defaultTerrain: terrainGround,
		terrainCells:   map[cell]terrain{{2, 2}: terrainUnderwater},
	}

	if got := state.terrainAt(cell{0, 0}); got != terrainGround {
		t.Fatalf("a cell with no override: %v", got)
	}
	if got := state.terrainAt(cell{2, 2}); got != terrainUnderwater {
		t.Fatalf("a cell with an override: %v", got)
	}
}

func TestAUnitStandsOnTheTerrainOfItsAnchorCell(t *testing.T) {
	state := &Board{
		bounds:         bounds{Low: cell{0, 0}, High: cell{4, 4}},
		defaultTerrain: terrainSurface,
		terrainCells:   map[cell]terrain{{1, 1}: terrainUnderwater, {2, 1}: terrainGround},
		units: []unit{
			{ID: "a1", Faction: factionAlly, HP: 1,
				Footprint: footprint{Anchor: cell{1, 1}, Size: size{2, 2}}},
			{ID: "e1", Faction: factionEnemy, HP: 1,
				Footprint: footprint{Anchor: cell{3, 3}, Size: size{1, 1}}},
		},
	}

	if got := state.terrainOf(state.unit("a1")); got != terrainUnderwater {
		t.Fatalf("the anchor cell holds the terrain of the unit: %v", got)
	}
	if got := state.terrainOf(state.unit("e1")); got != terrainSurface {
		t.Fatalf("a unit off every override: %v", got)
	}
}

func TestABoardWithNoTerrainReadsSpace(t *testing.T) {
	state, err := newBoard(bounds{Low: cell{0, 0}, High: cell{4, 4}}, nil)
	if err != nil {
		t.Fatalf("board: %v", err)
	}

	if got := state.terrainAt(cell{3, 1}); got != terrainSpace {
		t.Fatalf("the zero value of the board: %v", got)
	}
}

func TestAPayloadWithNoTerrainDecodesToNoRestriction(t *testing.T) {
	state, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if state.defaultTerrain != terrainSpace || state.terrainCells != nil {
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
