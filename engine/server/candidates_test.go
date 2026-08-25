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

func capabilitiesOf(t *testing.T, reply reply) protocol.ActionsResponse {
	t.Helper()
	if !reply.OK {
		t.Fatalf("actions: %+v", reply)
	}
	var payload protocol.ActionsResponse
	if err := json.Unmarshal(reply.Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	return payload
}

func TestActionsWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), `{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestActionsAnswersThePanelAndTheCellsOfTheLoadedBoard(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	payload := capabilitiesOf(t, replies[1])
	if payload.Unit.UnitID != "a1" || payload.Unit.Pos != (protocol.Cell{1, 1}) ||
		payload.Unit.Acted {
		t.Fatalf("status: %+v", payload.Unit)
	}
	if len(payload.MoveCells) != 1 || payload.MoveCells[0] != (protocol.Cell{1, 1}) {
		t.Fatalf("a unit with no move range holds its own cell: %+v", payload.MoveCells)
	}
	if len(payload.Weapons) != 2 || payload.Weapons[0].Name != "rifle" ||
		payload.Weapons[0].RangeMax != 2 {
		t.Fatalf("weapons: %+v", payload.Weapons)
	}
	if payload.Weapons[0].Ammo != nil {
		t.Fatalf("the rifle spends no ammunition: %+v", payload.Weapons[0])
	}
	if payload.Weapons[1].Ammo == nil || *payload.Weapons[1].Ammo != 1 {
		t.Fatalf("shells: %+v", payload.Weapons[1])
	}
	if payload.Error != nil {
		t.Fatalf("error: %+v", payload.Error)
	}
}

// The band and the energy stay out of the answer: unit 'a1' reaches the foe
// with the rifle alone, and both weapons are in the list.
func TestActionsJudgesNoTargetAndNoResource(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	payload := capabilitiesOf(t, replies[1])

	if len(payload.Weapons) != 2 {
		t.Fatalf("weapons: %+v", payload.Weapons)
	}
	if strings.Contains(string(replies[1].Payload), `"target_id"`) {
		t.Fatalf("the answer names no target: %s", replies[1].Payload)
	}
}

func TestActionsOfAnUnknownUnitIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"ghost"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActionsOutsideThePhaseIsAnIllegalState(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"e1"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("the phase is the ally side: %+v", replies[1])
	}
}

func TestActionsOfAnActedUnitAnswersWithTheStateInThePayload(t *testing.T) {
	replies := serve(t, New(), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a2"}}`)

	payload := capabilitiesOf(t, replies[1])

	if !payload.Unit.Acted || payload.Error == nil ||
		payload.Error.Code != protocol.CodeAlreadyActed {
		t.Fatalf("unit 'a2' acted: %+v", payload)
	}
	if len(payload.MoveCells) == 0 {
		t.Fatalf("the payload of an acted unit stays whole: %+v", payload)
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
