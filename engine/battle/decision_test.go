package battle

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestTheStanceNoneDecodes(t *testing.T) {
	var responseAttack ResponseAttack

	if err := json.Unmarshal([]byte(`{"stance":"none"}`), &responseAttack); err != nil {
		t.Fatalf("error: %v", err)
	}
	if responseAttack.Stance != StanceNone {
		t.Fatalf("stance: %v", responseAttack.Stance)
	}
	if err := json.Unmarshal([]byte(`{"stance":"flee"}`), &responseAttack); err == nil ||
		!strings.Contains(err.Error(), `stance "flee"`) {
		t.Fatalf("a stance outside the contract: %v", err)
	}
}

func TestAnAbsentOptionalFieldDecodesToTheSameValueAsNull(t *testing.T) {
	var absent, null Decision

	if err := json.Unmarshal([]byte(`{"unit_id":0,"kind":"standby"}`), &absent); err != nil {
		t.Fatalf("absent: %v", err)
	}
	body := `{"unit_id":0,"kind":"standby","move_to":null,"target_id":null,"weapon_id":null,` +
		`"map_weapon_id":null,"amount":null,"response_attack":null,"aim":null,"hit":null,` +
		`"counter_hit":null,"support_hit":null}`
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
		var decision Decision
		line := `{"unit_id":0,"kind":"attack","hit":` + body + `}`
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
