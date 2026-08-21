package server

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const candidateLine = `{"id":"l1","cmd":"load","payload":{"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100,"max_hp":100,` +
	`"weapons":[` +
	`{"name":"rifle","range_min":1,"range_max":2,"can_counter":true,"usable_after_move":true},` +
	`{"name":"shells","range_min":1,"range_max":3,"map_weapon":true,"usable_after_move":true}],` +
	`"ammo":{"shells":1}},` +
	`{"unit_id":"a2","faction":"ally","pos":[4,4],"hp":100,"acted":true},` +
	`{"unit_id":"e1","faction":"enemy","pos":[2,1],"hp":100,` +
	`"weapons":[{"name":"lance","range_min":1,"range_max":1,"can_counter":true}]}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[4,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func actionsOf(t *testing.T, reply reply) []protocol.Decision {
	t.Helper()
	if !reply.OK {
		t.Fatalf("actions: %+v", reply)
	}
	var payload protocol.ActionsResponse
	if err := json.Unmarshal(reply.Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	return payload.Actions
}

func TestActionsWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), `{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestActionsAnswersTheCandidatesOfTheLoadedBoard(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	actions := actionsOf(t, replies[1])
	kinds := make([]protocol.ActionKind, 0, len(actions))
	for _, action := range actions {
		kinds = append(kinds, action.Kind)
	}
	want := []protocol.ActionKind{protocol.ActionAttack, protocol.ActionMapAttack,
		protocol.ActionStandby}
	if len(kinds) != len(want) {
		t.Fatalf("actions: %v", kinds)
	}
	for index, kind := range want {
		if kinds[index] != kind {
			t.Fatalf("actions: %v", kinds)
		}
	}
	if *actions[0].TargetID != "e1" || *actions[0].Weapon != "rifle" {
		t.Fatalf("attack: %+v", actions[0])
	}
	if !strings.Contains(string(replies[1].Payload), `"hit":null`) {
		t.Fatalf("an enumerated action settles no die: %s", replies[1].Payload)
	}
}

func TestActionsOfAnUnknownUnitIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"ghost"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActionsOutsideThePhaseOrAfterTheActivationIsAnIllegalState(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"e1"}}`,
		`{"id":"c2","cmd":"actions","payload":{"unit_id":"a2"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("the phase is the ally side: %+v", replies[1])
	}
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("unit 'a2' acted: %+v", replies[2])
	}
}

func TestReactionsWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(),
		`{"id":"r1","cmd":"reactions","payload":{"defender_id":"e1","attacker_id":"a1",`+
			`"attacker_cell":[1,1],"weapon_id":"rifle"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestReactionsAnswersTheOptionsOfTheDefender(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"r1","cmd":"reactions","payload":{"defender_id":"e1","attacker_id":"a1",`+
			`"attacker_cell":[1,1],"weapon_id":"rifle"}}`)

	if !replies[1].OK {
		t.Fatalf("reactions: %+v", replies[1])
	}
	var payload protocol.ReactionsResponse
	if err := json.Unmarshal(replies[1].Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	if len(payload.Reactions) != 3 {
		t.Fatalf("reactions: %+v", payload.Reactions)
	}
	if payload.Reactions[2].Stance != protocol.StanceCounter ||
		*payload.Reactions[2].Weapon != "lance" {
		t.Fatalf("counter: %+v", payload.Reactions[2])
	}
}

func TestReactionsAgainstAMapWeaponIsAnEmptyList(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"r1","cmd":"reactions","payload":{"defender_id":"e1","attacker_id":"a1",`+
			`"attacker_cell":[1,1],"weapon_id":"shells"}}`)

	if !replies[1].OK {
		t.Fatalf("reactions: %+v", replies[1])
	}
	if !strings.Contains(string(replies[1].Payload), `"reactions":[]`) {
		t.Fatalf("an empty list is no null: %s", replies[1].Payload)
	}
}

func TestAReactionRequestThatTheWeaponDoesNotReachIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"r1","cmd":"reactions","payload":{"defender_id":"e1","attacker_id":"a1",`+
			`"attacker_cell":[4,4],"weapon_id":"rifle"}}`,
		`{"id":"r2","cmd":"reactions","payload":{"defender_id":"e1","attacker_id":"a1",`+
			`"attacker_cell":[1,1],"weapon_id":"lance"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("the cell (4,4) stands outside the band: %+v", replies[1])
	}
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("unit 'a1' carries no weapon 'lance': %+v", replies[2])
	}
}
