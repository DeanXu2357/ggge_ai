package board

import "testing"

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
