package board

import (
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var everyTerrain = []battle.Terrain{
	battle.TerrainSpace,
	battle.TerrainAtmospheric,
	battle.TerrainGround,
	battle.TerrainSurface,
	battle.TerrainUnderwater,
}

func TestEveryTerrainCarriesItsWireName(t *testing.T) {
	want := []string{"space", "atmospheric", "ground", "surface", "underwater"}

	for index, kind := range everyTerrain {
		if string(kind) != want[index] {
			t.Fatalf("name of %v: %q, want %q", kind, string(kind), want[index])
		}
		var parsed battle.Terrain
		if err := json.Unmarshal([]byte(`"`+want[index]+`"`), &parsed); err != nil {
			t.Fatalf("parse %q: %v", want[index], err)
		}
		if parsed != kind {
			t.Fatalf("parse %q: %v", want[index], parsed)
		}
	}
}

func TestAnEmptyTerrainNameReadsAsSpaceAndAnUnknownOneIsRefused(t *testing.T) {
	var empty battle.Terrain
	if err := json.Unmarshal([]byte(`""`), &empty); err != nil {
		t.Fatalf("the empty name is the terrain that a state leaves out: %v", err)
	}
	for _, name := range []string{"Space", "orbit"} {
		var parsed battle.Terrain
		if err := json.Unmarshal([]byte(`"`+name+`"`), &parsed); err == nil {
			t.Fatalf("the decode took %q", name)
		}
	}
}
