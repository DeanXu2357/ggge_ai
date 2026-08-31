package battle

import (
	"encoding/json"
	"reflect"
	"testing"
)

var everyTerrain = []Terrain{
	TerrainSpace,
	TerrainAtmospheric,
	TerrainGround,
	TerrainSurface,
	TerrainUnderwater,
}

func TestAFootprintIsWithinTheBoardOnlyAsAWhole(t *testing.T) {
	bounds := Bounds{{0, 0}, {4, 4}}

	if !(Footprint{Anchor: Cell{3, 3}, Size: Cell{2, 2}}).Within(bounds) {
		t.Fatal("the anchor (3,3) holds a footprint of 2 by 2 on a board of 5 by 5")
	}
	if (Footprint{Anchor: Cell{4, 3}, Size: Cell{2, 2}}).Within(bounds) {
		t.Fatal("an anchor on the last column puts half of the footprint outside")
	}
	if (Footprint{Anchor: Cell{-1, 0}, Size: Cell{1, 1}}).Within(bounds) {
		t.Fatal("a cell below the low corner is outside")
	}
}

func TestAFootprintKnowsItsCells(t *testing.T) {
	footprint := Footprint{Anchor: Cell{1, 1}, Size: Cell{2, 3}}

	want := []Cell{{1, 1}, {1, 2}, {1, 3}, {2, 1}, {2, 2}, {2, 3}}
	if got := footprint.Cells(); !reflect.DeepEqual(got, want) {
		t.Fatalf("cells: %v", got)
	}
}

func TestTheOpposingFactionOfEverySide(t *testing.T) {
	if FactionAlly.Opposing() != FactionEnemy {
		t.Fatal("the ally side fights the enemy side")
	}
	if FactionEnemy.Opposing() != FactionAlly ||
		FactionThirdParty.Opposing() != FactionAlly {
		t.Fatal("the enemy side and a third party fight the ally side")
	}
}

func TestEveryTerrainCarriesItsWireName(t *testing.T) {
	want := []string{"space", "atmospheric", "ground", "surface", "underwater"}

	for index, kind := range everyTerrain {
		if string(kind) != want[index] {
			t.Fatalf("name of %v: %q, want %q", kind, string(kind), want[index])
		}
		var parsed Terrain
		if err := json.Unmarshal([]byte(`"`+want[index]+`"`), &parsed); err != nil {
			t.Fatalf("parse %q: %v", want[index], err)
		}
		if parsed != kind {
			t.Fatalf("parse %q: %v", want[index], parsed)
		}
	}
}

func TestAnEmptyTerrainNameReadsAsSpaceAndAnUnknownOneIsRefused(t *testing.T) {
	var empty Terrain
	if err := json.Unmarshal([]byte(`""`), &empty); err != nil {
		t.Fatalf("the empty name is the terrain that a state leaves out: %v", err)
	}
	for _, name := range []string{"Space", "orbit"} {
		var parsed Terrain
		if err := json.Unmarshal([]byte(`"`+name+`"`), &parsed); err == nil {
			t.Fatalf("the decode took %q", name)
		}
	}
}
