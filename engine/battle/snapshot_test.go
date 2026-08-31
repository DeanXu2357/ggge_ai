package battle

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestAValueOutsideAnEnumIsADecodeError(t *testing.T) {
	var unit Unit
	var decision Decision
	var skill Skill
	var area MapWeapon
	var shape ShapeRange

	faction := json.Unmarshal([]byte(`{"faction":"neutral"}`), &unit)
	kind := json.Unmarshal([]byte(`{"kind":"charge"}`), &decision)
	source := json.Unmarshal([]byte(`{"source":"squad"}`), &skill)
	affects := json.Unmarshal([]byte(`{"affects":"self"}`), &skill)
	audience := json.Unmarshal([]byte(`{"affects":"self"}`), &area)
	direction := json.Unmarshal([]byte(`{"direction":"north"}`), &shape)

	if faction == nil || kind == nil || source == nil || affects == nil ||
		audience == nil || direction == nil {
		t.Fatalf("faction: %v, kind: %v, source: %v, affects: %v, audience: %v, direction: %v",
			faction, kind, source, affects, audience, direction)
	}
}

func TestAMapWeaponOfAMechSurvivesTheRoundTrip(t *testing.T) {
	mech := Mech{
		MoveRange: 4,
		Weapons:   []Weapon{{Name: "rifle", RangeMin: 1, RangeMax: 3}},
		MapWeapons: []MapWeapon{{
			Name:        "shells",
			Power:       1800,
			ApplyShape:  ShapeRange{Cells: []Cell{{0, 0}, {1, 0}, {1, 1}}, Direction: DirectionRight},
			EffectShape: ShapeRange{Cells: []Cell{{0, 2}, {2, 0}}, Direction: DirectionNone},
			AmmoMax:     2,
			ENCost:      5,
			Affects:     MapWeaponAffectsAll,
		}},
	}

	raw, err := json.Marshal(mech)
	if err != nil {
		t.Fatal(err)
	}
	var back Mech
	if err := json.Unmarshal(raw, &back); err != nil {
		t.Fatal(err)
	}

	if !reflect.DeepEqual(back, mech) {
		t.Fatalf("the round trip changed the mech: %+v", back)
	}
	area := back.MapWeapons[0]
	if area.ApplyShape.Direction != DirectionRight || len(area.ApplyShape.Cells) != 3 ||
		len(area.EffectShape.Cells) != 2 || area.Affects != MapWeaponAffectsAll {
		t.Fatalf("map weapon: %+v", area)
	}
}

func TestBoundsCarryTwoCellsOrNothing(t *testing.T) {
	var open, closed BattleState

	if err := json.Unmarshal([]byte(`{"turn":1,"bounds":null}`), &open); err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := json.Unmarshal([]byte(`{"turn":1,"bounds":[[0,0],[5,4]]}`), &closed); err != nil {
		t.Fatalf("closed: %v", err)
	}

	if open.Bounds != nil {
		t.Fatalf("bounds: %v", open.Bounds)
	}
	if closed.Bounds == nil || *closed.Bounds != (Bounds{{0, 0}, {5, 4}}) {
		t.Fatalf("bounds: %v", closed.Bounds)
	}
}
