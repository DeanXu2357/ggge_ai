package server

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const boardLine = `{"id":"l1","cmd":"load","payload":{"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[2,2],"hp":100,"move_range":2},` +
	`{"unit_id":"e1","faction":"enemy","pos":[2,3],"hp":100}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[4,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func TestReachWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), `{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestReachAnswersTheCellsOfTheLoadedBoard(t *testing.T) {
	replies := serve(t, New(), boardLine, `{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

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
	want := []protocol.Cell{
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
		`{"unit_id":"a1","faction":"ally","pos":[0,0],"size":[2,2],"hp":100,"move_range":1},` +
		`{"unit_id":"e1","faction":"enemy","pos":[2,1],"hp":100}` +
		`],"phase":"ally","turn":1,"bounds":[[0,0],[4,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`

	replies := serve(t, New(), line, `{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if !replies[1].OK {
		t.Fatalf("reach: %+v", replies[1])
	}
	var payload protocol.ReachResponse
	if err := json.Unmarshal(replies[1].Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	want := []protocol.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(payload.Cells, want) {
		t.Fatalf("cells: %v", payload.Cells)
	}
}

func TestReachOfAnUnknownUnitIsAnIllegalAction(t *testing.T) {
	replies := serve(t, New(), boardLine, `{"id":"r1","cmd":"reach","payload":{"unit_id":"ghost"}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestLoadRefusesAPayloadOutsideTheContract(t *testing.T) {
	replies := serve(t, New(),
		`{"id":"l1","cmd":"load","payload":{"state":{"units":[{"faction":"pirate"}]}}}`,
		`{"id":"r1","cmd":"reach","payload":{"unit_id":"a1"}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("load: %+v", replies[0])
	}
	if replies[1].Error.Code != protocol.CodeNoSession {
		t.Fatalf("a refused load holds no board: %+v", replies[1])
	}
}

const initLine = `{"id":"i1","cmd":"init","payload":{` +
	`"board":{"width":6,"height":5,"terrain":"ground",` +
	`"terrain_cells":[{"cell":[1,1],"terrain":"underwater"}]},` +
	`"enemies":[{"unit_id":"e1","faction":"enemy","pos":[3,0],"hp":100,"max_hp":100}],` +
	`"victory":[{"kind":"destroy_all"}],` +
	`"events":{"boss":{"event_id":"boss",` +
	`"trigger":{"type":"turn_start","turn":3},` +
	`"effect":{"type":"weaken","uids":["e1"],"attack_multiplier":0.5}}},` +
	`"deploy_cells":[[0,0],[0,1]],` +
	`"rules":{"defend_multiplier":0.8,"shield_multiplier":0.6,` +
	`"support_defend_multiplier":0.8,"dodge_hit_penalty":20,"terrain":1,` +
	`"max_support_attackers":2,"en_regen_fraction":0.2},"seed":9}}`

func TestInitBuildsTheBoardOfTheStage(t *testing.T) {
	replies := serve(t, New(), initLine, `{"id":"x1","cmd":"export","payload":{}}`)

	var opened protocol.InitResponse
	if err := json.Unmarshal(replies[0].Payload, &opened); err != nil {
		t.Fatalf("init: %+v %v", replies[0].Error, err)
	}
	if opened.Turn != 1 || opened.Phase != protocol.FactionAlly || !opened.DeployOpen {
		t.Fatalf("opening: %+v", opened)
	}
	var snapshot protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &snapshot); err != nil {
		t.Fatalf("export: %v", err)
	}
	if !reflect.DeepEqual(*snapshot.State.Bounds, protocol.Bounds{{0, 0}, {5, 4}}) {
		t.Fatalf("bounds: %v", snapshot.State.Bounds)
	}
	if snapshot.State.Terrain != "ground" || len(snapshot.State.TerrainCells) != 1 {
		t.Fatalf("terrain: %q %v", snapshot.State.Terrain, snapshot.State.TerrainCells)
	}
	if !reflect.DeepEqual(snapshot.State.PendingEvents, []string{"boss"}) {
		t.Fatalf("pending events: %v", snapshot.State.PendingEvents)
	}
	if snapshot.Rules.ENRegenFraction != 0.2 || snapshot.Seed != 9 {
		t.Fatalf("rules %+v, seed %d", snapshot.Rules, snapshot.Seed)
	}
}

func TestInitRefusesABoardWithNoRoom(t *testing.T) {
	line := `{"id":"i1","cmd":"init","payload":{"board":{"width":0,"height":5},` +
		`"enemies":[],"victory":[],"deploy_cells":[],"seed":0}}`

	replies := serve(t, New(), line)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestInitRefusesAnAllyUnitAmongTheEnemies(t *testing.T) {
	line := `{"id":"i1","cmd":"init","payload":{"board":{"width":6,"height":5},` +
		`"enemies":[{"unit_id":"a1","faction":"ally","pos":[0,0],"hp":100}],` +
		`"victory":[],"deploy_cells":[],"seed":0}}`

	replies := serve(t, New(), line)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestExportWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), `{"id":"x1","cmd":"export","payload":{}}`)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

// The snapshot of the session goes back into 'load' and comes out again.
func TestTheSnapshotOfASessionSurvivesTheRoundTrip(t *testing.T) {
	first := serve(t, New(), initLine, `{"id":"x1","cmd":"export","payload":{}}`)

	engine := New()
	replies := serve(t, engine,
		`{"id":"l1","cmd":"load","payload":`+string(first[1].Payload)+`}`,
		`{"id":"x2","cmd":"export","payload":{}}`)

	if !replies[0].OK {
		t.Fatalf("load: %+v", replies[0].Error)
	}
	if string(replies[1].Payload) != string(first[1].Payload) {
		t.Fatalf("the snapshot parted:\n%s\n%s", first[1].Payload, replies[1].Payload)
	}
}

func TestLoadRefusesAnEventTableThatTheTurnCycleCannotRun(t *testing.T) {
	line := strings.Replace(boardLine, `"history":[]`,
		`"history":[],"events":{"e":{"event_id":"e","trigger":{"type":"rain"},`+
			`"effect":{"type":"spawn"}}}`, 1)

	replies := serve(t, New(), line)

	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}
