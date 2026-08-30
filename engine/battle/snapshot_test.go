package battle

import (
	"encoding/json"
	"testing"
)

func TestAValueOutsideAnEnumIsADecodeError(t *testing.T) {
	var unit Unit
	var decision Decision
	var skill Skill

	faction := json.Unmarshal([]byte(`{"faction":"neutral"}`), &unit)
	kind := json.Unmarshal([]byte(`{"kind":"charge"}`), &decision)
	source := json.Unmarshal([]byte(`{"source":"squad"}`), &skill)
	affects := json.Unmarshal([]byte(`{"affects":"self"}`), &skill)

	if faction == nil || kind == nil || source == nil || affects == nil {
		t.Fatalf("faction: %v, kind: %v, source: %v, affects: %v", faction, kind, source, affects)
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
