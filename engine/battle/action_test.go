package battle

import (
	"encoding/json"
	"testing"
)

func TestAnAbsentStatedBehaviorDecodesToNil(t *testing.T) {
	var attack Attack

	if err := json.Unmarshal([]byte(`{"weapon_id":0,"target_id":1}`), &attack); err != nil {
		t.Fatalf("absent: %v", err)
	}
	if attack.Stated != nil {
		t.Fatalf("an absent 'stated' is a strike the board draws: %+v", attack.Stated)
	}
	if err := json.Unmarshal([]byte(`{"weapon_id":0,"target_id":1,"stated":null}`), &attack); err != nil {
		t.Fatalf("null: %v", err)
	}
	if attack.Stated != nil {
		t.Fatalf("a null 'stated' is the same strike: %+v", attack.Stated)
	}
	if err := json.Unmarshal([]byte(`{"weapon_id":0,"target_id":1,"stated":{"hit":true}}`), &attack); err != nil {
		t.Fatalf("stated: %v", err)
	}
	if attack.Stated == nil || !attack.Stated.Hit || attack.Stated.Crit {
		t.Fatalf("stated: %+v", attack.Stated)
	}
}

func TestAnActionWithNoSideDecodesToNilSides(t *testing.T) {
	var action Action

	if err := json.Unmarshal([]byte(`{"actor_id":2}`), &action); err != nil {
		t.Fatalf("error: %v", err)
	}
	if action.ActorID != 2 || action.Attack != nil ||
		action.ResponseAttack != nil || action.MoveTo != nil {
		t.Fatalf("action: %+v", action)
	}
}
