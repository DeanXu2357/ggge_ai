package server

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const candidateLine = `{"id":"l1","cmd":"load","payload":{"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100,"max_hp":100,` +
	`"mech":{"weapons":[` +
	`{"name":"rifle","range_min":1,"range_max":2,"usable_after_move":true}],` +
	`"map_weapons":[{"name":"shells","origin":"self","affects":"enemy",` +
	`"shape":{"cells":[[0,0]],"direction":"none"},"usable_after_move":true}]},` +
	`"ammo":{"shells":1}},` +
	`{"unit_id":"a2","faction":"ally","pos":[4,4],"hp":100,"acted":true},` +
	`{"unit_id":"e1","faction":"enemy","pos":[2,1],"hp":100,` +
	`"mech":{"weapons":[{"name":"lance","range_min":1,"range_max":1}]}}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[4,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func actionsOf(t *testing.T, reply reply) battle.ActionsResponse {
	t.Helper()
	if !reply.OK {
		t.Fatalf("actions: %+v", reply)
	}
	var payload battle.ActionsResponse
	if err := json.Unmarshal(reply.Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	return payload
}

func TestActionsWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(board.New()), `{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestActionsAnswersThePanelAndTheCellsOfTheLoadedBoard(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	payload := actionsOf(t, replies[1])
	if payload.Unit.UnitID != "a1" || payload.Unit.Pos != (battle.Cell{1, 1}) ||
		payload.Unit.Acted {
		t.Fatalf("status: %+v", payload.Unit)
	}
	if len(payload.MoveCells) != 1 || payload.MoveCells[0] != (battle.Cell{1, 1}) {
		t.Fatalf("a unit with no move range holds its own cell: %+v", payload.MoveCells)
	}
	if len(payload.Weapons) != 1 || payload.Weapons[0].Name != "rifle" ||
		payload.Weapons[0].RangeMax != 2 {
		t.Fatalf("weapons: %+v", payload.Weapons)
	}
	if len(payload.MapWeapons) != 1 || payload.MapWeapons[0].Name != "shells" {
		t.Fatalf("map weapons: %+v", payload.MapWeapons)
	}
	if payload.MapWeapons[0].Ammo == nil || *payload.MapWeapons[0].Ammo != 1 {
		t.Fatalf("shells: %+v", payload.MapWeapons[0])
	}
}

// The band and the energy stay out of the answer: unit 'a1' reaches the foe
// with the rifle alone, and both weapons are in their lists.
func TestActionsJudgesNoTargetAndNoResource(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a1"}}`)

	payload := actionsOf(t, replies[1])

	if len(payload.Weapons) != 1 || len(payload.MapWeapons) != 1 {
		t.Fatalf("weapons: %+v, map weapons: %+v", payload.Weapons, payload.MapWeapons)
	}
	if strings.Contains(string(replies[1].Payload), `"target_id"`) {
		t.Fatalf("the answer names no target: %s", replies[1].Payload)
	}
}

func TestActionsOfAnUnknownUnitIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"ghost"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActionsOutsideThePhaseIsAnIllegalState(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"e1"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("the phase is the ally side: %+v", replies[1])
	}
}

func TestActionsOfAnActedUnitIsAnIllegalState(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"c1","cmd":"actions","payload":{"unit_id":"a2"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("unit 'a2' acted: %+v", replies[1])
	}
}

func TestResponseAttacksWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(board.New()),
		`{"id":"r1","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"attack","target_id":"e1","weapon":"rifle"}}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func engagementOf(t *testing.T, reply reply) battle.ResponseAttacksResponse {
	t.Helper()
	if !reply.OK {
		t.Fatalf("response attacks: %+v", reply)
	}
	var payload battle.ResponseAttacksResponse
	if err := json.Unmarshal(reply.Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	return payload
}

func TestResponseAttacksAnswersTheOptionsOfTheDefender(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"r1","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"attack","target_id":"e1",`+
			`"weapon":"rifle","move_to":[1,1]}}}`)

	payload := engagementOf(t, replies[1])

	if payload.Defender.UnitID != "e1" || payload.Attacker.UnitID != "a1" {
		t.Fatalf("sides: %+v", payload)
	}
	want := []battle.Stance{battle.StanceDodge, battle.StanceDefend,
		battle.StanceCounter, battle.StanceNone}
	if len(payload.Defender.ResponseAttacks) != len(want) {
		t.Fatalf("response attacks: %+v", payload.Defender.ResponseAttacks)
	}
	for index, stance := range want {
		if payload.Defender.ResponseAttacks[index].Stance != stance {
			t.Fatalf("response attacks: %+v", payload.Defender.ResponseAttacks)
		}
	}
	if *payload.Defender.ResponseAttacks[2].Weapon != "lance" ||
		payload.Defender.ResponseAttacks[2].Counter == nil {
		t.Fatalf("counter: %+v", payload.Defender.ResponseAttacks[2])
	}
	for index, option := range payload.Defender.ResponseAttacks {
		if option.Incoming.HitRate == nil || option.Incoming.Damage == nil ||
			option.Incoming.Kill == nil {
			t.Fatalf("the entry %d carries no forecast: %+v", index, option.Incoming)
		}
	}
}

func TestResponseAttacksAgainstAnActionThatMakesNoStrikeIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"r1","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"map_attack","weapon":"shells"}}}`,
		`{"id":"r2","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"standby"}}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("a map attack permits no response attack: %+v", replies[1])
	}
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("a standby asks the defender nothing: %+v", replies[2])
	}
}

func TestAResponseAttackRequestThatTheWeaponDoesNotReachIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"r1","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"attack","weapon":"rifle","move_to":[4,4]}}}`,
		`{"id":"r2","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"attack","weapon":"lance"}}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("the cell (4,4) stands outside the band: %+v", replies[1])
	}
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("unit 'a1' carries no weapon 'lance': %+v", replies[2])
	}
}

func TestAnActionOutsideTheContractIsABadRequest(t *testing.T) {
	replies := serve(t, New(board.New()), candidateLine,
		`{"id":"r1","cmd":"response_attacks","payload":{"defender_id":"e1",`+
			`"action":{"unit_id":"a1","kind":"charge","weapon":"rifle"}}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("the kind \"charge\" is not in the contract: %+v", replies[1])
	}
}
