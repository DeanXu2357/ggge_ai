package battle

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var everyTerrain = []Terrain{
	TerrainSpace,
	TerrainAtmospheric,
	TerrainGround,
	TerrainSurface,
	TerrainUnderwater,
}

func TestEveryTerrainCarriesItsWireName(t *testing.T) {
	want := []string{"space", "atmospheric", "ground", "surface", "underwater"}

	for index, kind := range everyTerrain {
		if got := kind.String(); got != want[index] {
			t.Fatalf("name of %d: %q, want %q", int(kind), got, want[index])
		}
		parsed, err := ParseTerrain(want[index])
		if err != nil {
			t.Fatalf("parse %q: %v", want[index], err)
		}
		if parsed != kind {
			t.Fatalf("parse %q: %v", want[index], parsed)
		}
	}
}

func TestParseRefusesATerrainOutsideTheContract(t *testing.T) {
	for _, name := range []string{"", "Space", "水中", "orbit"} {
		if _, err := ParseTerrain(name); err == nil {
			t.Fatalf("the parse took %q", name)
		}
	}
}

func TestACellTakesTheTerrainOfTheBoardOrItsOwn(t *testing.T) {
	board := &Board{
		Bounds:         Bounds{Low: Cell{0, 0}, High: Cell{4, 4}},
		DefaultTerrain: TerrainGround,
		TerrainCells:   map[Cell]Terrain{{2, 2}: TerrainUnderwater},
	}

	if got := board.TerrainAt(Cell{0, 0}); got != TerrainGround {
		t.Fatalf("a cell with no override: %v", got)
	}
	if got := board.TerrainAt(Cell{2, 2}); got != TerrainUnderwater {
		t.Fatalf("a cell with an override: %v", got)
	}
}

func TestAUnitStandsOnTheTerrainOfItsAnchorCell(t *testing.T) {
	board := &Board{
		Bounds:         Bounds{Low: Cell{0, 0}, High: Cell{4, 4}},
		DefaultTerrain: TerrainSurface,
		TerrainCells:   map[Cell]Terrain{{1, 1}: TerrainUnderwater, {2, 1}: TerrainGround},
		Units: []Unit{
			{ID: "a1", Faction: FactionAlly, HP: 1,
				Footprint: Footprint{Anchor: Cell{1, 1}, Size: Size{2, 2}}},
			{ID: "e1", Faction: FactionEnemy, HP: 1,
				Footprint: Footprint{Anchor: Cell{3, 3}, Size: Size{1, 1}}},
		},
	}

	if got := board.TerrainOf(board.Unit("a1")); got != TerrainUnderwater {
		t.Fatalf("the anchor cell holds the terrain of the unit: %v", got)
	}
	if got := board.TerrainOf(board.Unit("e1")); got != TerrainSurface {
		t.Fatalf("a unit off every override: %v", got)
	}
}

func TestABoardWithNoTerrainReadsSpace(t *testing.T) {
	board, err := NewBoard(Bounds{Low: Cell{0, 0}, High: Cell{4, 4}}, nil)
	if err != nil {
		t.Fatalf("board: %v", err)
	}

	if got := board.TerrainAt(Cell{3, 1}); got != TerrainSpace {
		t.Fatalf("the zero value of the board: %v", got)
	}
}

func TestAPayloadWithNoTerrainDecodesToNoRestriction(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if board.DefaultTerrain != TerrainSpace || board.TerrainCells != nil {
		t.Fatalf("board: %v %v", board.DefaultTerrain, board.TerrainCells)
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
