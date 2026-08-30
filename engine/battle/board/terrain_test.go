package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func TestACellTakesTheTerrainOfTheBoardOrItsOwn(t *testing.T) {
	b := &Board{state: state.Board{
		Bounds:         state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{4, 4}},
		DefaultTerrain: state.TerrainGround,
		TerrainCells:   map[state.Cell]state.Terrain{{2, 2}: state.TerrainUnderwater},
	}}

	if got := b.terrainAt(state.Cell{0, 0}); got != state.TerrainGround {
		t.Fatalf("a cell with no override: %v", got)
	}
	if got := b.terrainAt(state.Cell{2, 2}); got != state.TerrainUnderwater {
		t.Fatalf("a cell with an override: %v", got)
	}
}

func TestAUnitStandsOnTheTerrainOfItsAnchorCell(t *testing.T) {
	b := &Board{state: state.Board{
		Bounds:         state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{4, 4}},
		DefaultTerrain: state.TerrainSurface,
		TerrainCells: map[state.Cell]state.Terrain{
			{1, 1}: state.TerrainUnderwater, {2, 1}: state.TerrainGround},
		Units: []state.Unit{
			{ID: "a1", Faction: state.FactionAlly, HP: 1,
				Footprint: state.Footprint{Anchor: state.Cell{1, 1}, Size: state.Size{2, 2}}},
			{ID: "e1", Faction: state.FactionEnemy, HP: 1,
				Footprint: state.Footprint{Anchor: state.Cell{3, 3}, Size: state.Size{1, 1}}},
		},
	}}

	if got := b.terrainOf(b.unit("a1")); got != state.TerrainUnderwater {
		t.Fatalf("the anchor cell holds the terrain of the unit: %v", got)
	}
	if got := b.terrainOf(b.unit("e1")); got != state.TerrainSurface {
		t.Fatalf("a unit off every override: %v", got)
	}
}

func TestABoardWithNoTerrainReadsSpace(t *testing.T) {
	b, err := newBoard(state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{4, 4}}, nil)
	if err != nil {
		t.Fatalf("board: %v", err)
	}

	if got := b.terrainAt(state.Cell{3, 1}); got != state.TerrainSpace {
		t.Fatalf("the zero value of the board: %v", got)
	}
}

func TestAPayloadWithNoTerrainDecodesToNoRestriction(t *testing.T) {
	b, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if b.state.DefaultTerrain != state.TerrainSpace || b.state.TerrainCells != nil {
		t.Fatalf("board: %v %v", b.state.DefaultTerrain, b.state.TerrainCells)
	}
}

func TestTheDecodeRefusesATerrainOutsideTheContract(t *testing.T) {
	cases := map[string]func(*battle.BattleState){
		"the map": func(wire *battle.BattleState) { wire.Terrain = "orbit" },
		"a cell": func(wire *battle.BattleState) {
			wire.TerrainCells = []battle.TerrainCell{{Cell: battle.Cell{1, 1}, Terrain: "lava"}}
		},
	}

	for name, spoil := range cases {
		t.Run(name, func(t *testing.T) {
			wire := wireBoard()
			spoil(wire)

			if _, err := DecodeState(wire); err == nil {
				t.Fatal("the decode took a terrain outside the contract")
			}
		})
	}
}
