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

func TestAWeaponWithNoRestrictionReachesEveryTerrain(t *testing.T) {
	weapon := Weapon{Name: "rifle"}

	for _, kind := range everyTerrain {
		if got := weapon.DamageScaleAgainst(kind); got != 1 {
			t.Fatalf("scale against %v: %v", kind, got)
		}
		if !weapon.UsableIn(kind) {
			t.Fatalf("the weapon does not fire in %v", kind)
		}
	}
}

func TestAWeaponHalvesAgainstTheTerrainItDeclares(t *testing.T) {
	weapon := Weapon{
		Name:          "beam rifle",
		TerrainDamage: map[Terrain]float64{TerrainUnderwater: 0.5},
	}

	for _, kind := range everyTerrain {
		want := 1.0
		if kind == TerrainUnderwater {
			want = 0.5
		}
		if got := weapon.DamageScaleAgainst(kind); got != want {
			t.Fatalf("scale against %v: %v, want %v", kind, got, want)
		}
		if !weapon.UsableIn(kind) {
			t.Fatalf("a damage entry stops the shot in %v", kind)
		}
	}
}

func TestAWeaponDoesNotFireFromTheTerrainItDeclares(t *testing.T) {
	weapon := Weapon{
		Name:       "beam cannon",
		UnusableIn: TerrainSet{TerrainUnderwater: true},
	}

	for _, kind := range everyTerrain {
		if got := weapon.UsableIn(kind); got != (kind != TerrainUnderwater) {
			t.Fatalf("usable in %v: %v", kind, got)
		}
		if got := weapon.DamageScaleAgainst(kind); got != 1 {
			t.Fatalf("a firing rule changed the scale against %v: %v", kind, got)
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

	weapon := board.Unit("a1").Weapons[0]
	if weapon.TerrainDamage != nil || weapon.UnusableIn != nil {
		t.Fatalf("weapon: %+v", weapon)
	}
	if board.DefaultTerrain != TerrainSpace || board.TerrainCells != nil {
		t.Fatalf("board: %v %v", board.DefaultTerrain, board.TerrainCells)
	}
}

func TestTheDecodeKeepsTheTerrainOfThePayload(t *testing.T) {
	state := wireBoard()
	state.Terrain = "surface"
	state.TerrainCells = []protocol.TerrainCell{{Cell: protocol.Cell{7, 7}, Terrain: "underwater"}}
	state.Units[0].Weapons[0].TerrainDamage = map[string]float64{"underwater": 0.5}
	state.Units[0].Weapons[0].UnusableIn = []string{"underwater"}

	board, err := DecodeState(state)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	weapon := board.Unit("a1").Weapons[0]
	if got := weapon.DamageScaleAgainst(board.TerrainOf(board.Unit("e1"))); got != 0.5 {
		t.Fatalf("scale against the enemy cell: %v", got)
	}
	if got := weapon.DamageScaleAgainst(board.TerrainOf(board.Unit("a1"))); got != 1 {
		t.Fatalf("scale against the ally cell: %v", got)
	}
	if !weapon.UsableIn(TerrainSurface) || weapon.UsableIn(TerrainUnderwater) {
		t.Fatal("the weapon fires on the surface and not under water")
	}
}

func TestTheDecodeRefusesATerrainOutsideTheContract(t *testing.T) {
	cases := map[string]func(*protocol.BattleState){
		"the map": func(state *protocol.BattleState) { state.Terrain = "orbit" },
		"a cell": func(state *protocol.BattleState) {
			state.TerrainCells = []protocol.TerrainCell{{Cell: protocol.Cell{1, 1}, Terrain: "lava"}}
		},
		"a weapon damage entry": func(state *protocol.BattleState) {
			state.Units[0].Weapons[0].TerrainDamage = map[string]float64{"lava": 0.5}
		},
		"a weapon firing entry": func(state *protocol.BattleState) {
			state.Units[0].Weapons[0].UnusableIn = []string{"lava"}
		},
		"a weapon of the mech base": func(state *protocol.BattleState) {
			state.Units[0].MechWeapons = []protocol.Weapon{
				{Name: "beam", TerrainDamage: map[string]float64{"lava": 0.5}},
			}
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
