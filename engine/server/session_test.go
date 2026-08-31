package server

import (
	"encoding/json"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const boardLine = `{"id":"l1","cmd":"load","payload":{"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[2,2],"hp":100,"mech":{"move_range":2}},` +
	`{"unit_id":"e1","faction":"enemy","pos":[2,3],"hp":100}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[4,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func TestReachWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(board.Factory{}), `{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestReachAnswersTheCellsOfTheLoadedBoard(t *testing.T) {
	replies := serve(t, New(board.Factory{}), boardLine, `{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if !replies[0].OK {
		t.Fatalf("load: %+v", replies[0])
	}
	if !replies[1].OK {
		t.Fatalf("reach: %+v", replies[1])
	}
	var payload protocol.ReachResponse
	if err := json.Unmarshal(replies[1].Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	want := []battle.Cell{
		{0, 2},
		{1, 1}, {1, 2}, {1, 3},
		{2, 0}, {2, 1}, {2, 2},
		{3, 1}, {3, 2}, {3, 3},
		{4, 2},
	}
	if !reflect.DeepEqual(payload.Cells, want) {
		t.Fatalf("cells: %v", payload.Cells)
	}
}

func TestReachAnswersTheAnchorsThatHoldTheWholeFootprint(t *testing.T) {
	line := `{"id":"l1","cmd":"load","payload":{"state":{` +
		`"units":[` +
		`{"unit_id":"a1","faction":"ally","pos":[0,0],"size":[2,2],"hp":100,"mech":{"move_range":1}},` +
		`{"unit_id":"e1","faction":"enemy","pos":[2,1],"hp":100}` +
		`],"phase":"ally","turn":1,"bounds":[[0,0],[4,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`

	replies := serve(t, New(board.Factory{}), line, `{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if !replies[1].OK {
		t.Fatalf("reach: %+v", replies[1])
	}
	var payload protocol.ReachResponse
	if err := json.Unmarshal(replies[1].Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	want := []battle.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(payload.Cells, want) {
		t.Fatalf("cells: %v", payload.Cells)
	}
}

func TestReachOfAnUnknownUnitIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(board.Factory{}), boardLine, `{"id":"r1","cmd":"reach","payload":{"unit_id":"ghost"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestLoadRefusesAPayloadOutsideTheContract(t *testing.T) {
	replies := serve(t, New(board.Factory{}),
		`{"id":"l1","cmd":"load","payload":{"state":{"units":[{"faction":"pirate"}]}}}`,
		`{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("load: %+v", replies[0])
	}
	if replies[1].Error.Code != protocol.CodeNoSession {
		t.Fatalf("a refused load holds no board: %+v", replies[1])
	}
}
