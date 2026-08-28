package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func TestACellTakesTheTerrainOfTheBoardOrItsOwn(t *testing.T) {
	state := &Board{
		bounds:         Bounds{Low: Cell{0, 0}, High: Cell{4, 4}},
		defaultTerrain: TerrainGround,
		terrainCells:   map[Cell]Terrain{{2, 2}: TerrainUnderwater},
	}

	if got := state.terrainAt(Cell{0, 0}); got != TerrainGround {
		t.Fatalf("a cell with no override: %v", got)
	}
	if got := state.terrainAt(Cell{2, 2}); got != TerrainUnderwater {
		t.Fatalf("a cell with an override: %v", got)
	}
}

func TestAUnitStandsOnTheTerrainOfItsAnchorCell(t *testing.T) {
	state := &Board{
		bounds:         Bounds{Low: Cell{0, 0}, High: Cell{4, 4}},
		defaultTerrain: TerrainSurface,
		terrainCells:   map[Cell]Terrain{{1, 1}: TerrainUnderwater, {2, 1}: TerrainGround},
		units: []Unit{
			{ID: "a1", Faction: FactionAlly, HP: 1,
				Footprint: Footprint{Anchor: Cell{1, 1}, Size: Size{2, 2}}},
			{ID: "e1", Faction: FactionEnemy, HP: 1,
				Footprint: Footprint{Anchor: Cell{3, 3}, Size: Size{1, 1}}},
		},
	}

	if got := state.terrainOf(state.unit("a1")); got != TerrainUnderwater {
		t.Fatalf("the anchor cell holds the terrain of the unit: %v", got)
	}
	if got := state.terrainOf(state.unit("e1")); got != TerrainSurface {
		t.Fatalf("a unit off every override: %v", got)
	}
}

func TestABoardWithNoTerrainReadsSpace(t *testing.T) {
	state, err := New(Bounds{Low: Cell{0, 0}, High: Cell{4, 4}}, nil)
	if err != nil {
		t.Fatalf("board: %v", err)
	}

	if got := state.terrainAt(Cell{3, 1}); got != TerrainSpace {
		t.Fatalf("the zero value of the board: %v", got)
	}
}

func TestAPayloadWithNoTerrainDecodesToNoRestriction(t *testing.T) {
	state, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if state.defaultTerrain != TerrainSpace || state.terrainCells != nil {
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
