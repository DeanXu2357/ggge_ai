package board

import (
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var everyTerrain = []state.Terrain{
	state.TerrainSpace,
	state.TerrainAtmospheric,
	state.TerrainGround,
	state.TerrainSurface,
	state.TerrainUnderwater,
}

func TestEveryTerrainCarriesItsWireName(t *testing.T) {
	want := []string{"space", "atmospheric", "ground", "surface", "underwater"}

	for index, kind := range everyTerrain {
		if got := terrainName(kind); got != want[index] {
			t.Fatalf("name of %d: %q, want %q", int(kind), got, want[index])
		}
		parsed, err := parseTerrain(want[index])
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
		if _, err := parseTerrain(name); err == nil {
			t.Fatalf("the parse took %q", name)
		}
	}
}
