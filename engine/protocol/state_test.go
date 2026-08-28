package protocol_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func TestTheStanceNoneDecodes(t *testing.T) {
	var responseAttack protocol.ResponseAttack

	if err := json.Unmarshal([]byte(`{"stance":"none"}`), &responseAttack); err != nil {
		t.Fatalf("error: %v", err)
	}
	if responseAttack.Stance != protocol.StanceNone {
		t.Fatalf("stance: %v", responseAttack.Stance)
	}
	if err := json.Unmarshal([]byte(`{"stance":"flee"}`), &responseAttack); err == nil ||
		!strings.Contains(err.Error(), `stance "flee"`) {
		t.Fatalf("a stance outside the contract: %v", err)
	}
}

func TestAValueOutsideAnEnumIsADecodeError(t *testing.T) {
	var unit protocol.Unit
	var decision protocol.Decision
	var skill protocol.Skill

	faction := json.Unmarshal([]byte(`{"faction":"neutral"}`), &unit)
	kind := json.Unmarshal([]byte(`{"kind":"charge"}`), &decision)
	source := json.Unmarshal([]byte(`{"source":"squad"}`), &skill)
	affects := json.Unmarshal([]byte(`{"affects":"self"}`), &skill)

	if faction == nil || kind == nil || source == nil || affects == nil {
		t.Fatalf("faction: %v, kind: %v, source: %v, affects: %v", faction, kind, source, affects)
	}
}

func TestAnAbsentOptionalFieldDecodesToTheSameValueAsNull(t *testing.T) {
	var absent, null protocol.Decision

	if err := json.Unmarshal([]byte(`{"unit_id":"a","kind":"standby"}`), &absent); err != nil {
		t.Fatalf("absent: %v", err)
	}
	body := `{"unit_id":"a","kind":"standby","move_to":null,"target_id":null,"weapon":null,` +
		`"amount":null,"response_attack":null,"aim":null,"hit":null,"counter_hit":null,` +
		`"support_hit":null}`
	if err := json.Unmarshal([]byte(body), &null); err != nil {
		t.Fatalf("null: %v", err)
	}

	first, _ := json.Marshal(absent)
	second, _ := json.Marshal(null)
	if string(first) != string(second) {
		t.Fatalf("%s\n%s", first, second)
	}
}

func TestAThreeValuedDieKeepsItsThreeValues(t *testing.T) {
	for _, body := range []string{`null`, `true`, `false`} {
		var decision protocol.Decision
		line := `{"unit_id":"a","kind":"attack","hit":` + body + `}`
		if err := json.Unmarshal([]byte(line), &decision); err != nil {
			t.Fatalf("%s: %v", body, err)
		}
		out, err := json.Marshal(decision)
		if err != nil {
			t.Fatalf("%s: %v", body, err)
		}
		if !strings.Contains(string(out), `"hit":`+body) {
			t.Fatalf("%s: %s", body, out)
		}
	}
}

func TestBoundsCarryTwoCellsOrNothing(t *testing.T) {
	var open, closed protocol.BattleState

	if err := json.Unmarshal([]byte(`{"turn":1,"bounds":null}`), &open); err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := json.Unmarshal([]byte(`{"turn":1,"bounds":[[0,0],[5,4]]}`), &closed); err != nil {
		t.Fatalf("closed: %v", err)
	}

	if open.Bounds != nil {
		t.Fatalf("bounds: %v", open.Bounds)
	}
	if closed.Bounds == nil || *closed.Bounds != (protocol.Bounds{{0, 0}, {5, 4}}) {
		t.Fatalf("bounds: %v", closed.Bounds)
	}
}
