package server

import (
	"encoding/json"
	"reflect"
	"strconv"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// The three units of the load stand at the positions 0, 1 and 2, and each
// position is the id of its unit.
const (
	firstAllyID  = 0
	secondAllyID = 1
	enemyID      = 2
)

const twoSidesLine = `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
	`"units":[` +
	`{"faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en":100,"en_max":140,"mech":{"move_range":1}},` +
	`{"faction":"ally","pos":[1,2],"hp":100,"max_hp":100,"en":100,"en_max":140,"mech":{"move_range":1}},` +
	`{"faction":"enemy","pos":[4,4],"hp":100,"max_hp":100,"en":100,"en_max":140}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func standby(id string, unit int) string {
	return `{"id":"` + id + `","cmd":"act","payload":{"actor_id":` + strconv.Itoa(unit) + `}}`
}

type actAnswer struct {
	Events  []json.RawMessage   `json:"events"`
	Units   []battle.UnitValues `json:"units"`
	Outcome battle.Outcome      `json:"outcome"`
	Board   battle.BoardSummary `json:"board"`
}

func decodeAct(t *testing.T, reply reply) actAnswer {
	t.Helper()
	if !reply.OK {
		t.Fatalf("act: %+v", reply)
	}
	var answer actAnswer
	if err := json.Unmarshal(reply.Payload, &answer); err != nil {
		t.Fatal(err)
	}
	return answer
}

func TestActWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(openBoard), standby("a", firstAllyID))
	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestAStandbyAnswersTheActivationEndAndThePendingSibling(t *testing.T) {
	replies := serve(t, New(openBoard), twoSidesLine, standby("a", firstAllyID))
	answer := decodeAct(t, replies[1])
	if len(answer.Events) != 1 || answer.Board.Turn != 1 || answer.Board.Phase != battle.FactionAlly {
		t.Fatalf("answer: %+v", answer)
	}
	if string(answer.Events[0]) != `{"event":"activation_end","actor_id":0,"effects":[{"unit_id":0,"acted":{"from":false,"to":true}}]}` {
		t.Fatalf("event: %s", answer.Events[0])
	}
	if len(answer.Units) != 1 || answer.Units[0].UnitID != firstAllyID || !answer.Units[0].Acted {
		t.Fatalf("terminal values: %+v", answer.Units)
	}
	if answer.Outcome != battle.OutcomeOngoing {
		t.Fatalf("outcome: %s", answer.Outcome)
	}
	if len(answer.Board.PendingIDs) != 1 || answer.Board.PendingIDs[0] != secondAllyID ||
		len(answer.Board.Gone) != 0 {
		t.Fatalf("summary: %+v", answer.Board)
	}
}

func TestTheLastActivationRotatesAndTheEventsSayWhere(t *testing.T) {
	replies := serve(t, New(openBoard), twoSidesLine,
		standby("a", firstAllyID), standby("b", secondAllyID))
	answer := decodeAct(t, replies[2])
	if answer.Board.Phase != battle.FactionEnemy || len(answer.Events) != 3 {
		t.Fatalf("answer: %+v", answer)
	}
	if string(answer.Events[1]) != `{"event":"phase","turn":1,"phase":"third_party","effects":[]}` {
		t.Fatalf("the empty phase: %s", answer.Events[1])
	}
	var last battle.PhaseEvent
	if err := json.Unmarshal(answer.Events[2], &last); err != nil {
		t.Fatal(err)
	}
	if last.Kind != battle.EventPhase || last.Turn != 1 || last.Phase != battle.FactionEnemy {
		t.Fatalf("last event: %s", answer.Events[2])
	}
	if len(last.Effects) != 1 || last.Effects[0].UnitID != enemyID || last.Effects[0].EN.To != 114 {
		t.Fatalf("the resets of the enemy side: %s", answer.Events[2])
	}
}

func TestAUnitOffPhaseIsIllegalState(t *testing.T) {
	replies := serve(t, New(openBoard), twoSidesLine, standby("a", enemyID))
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAUnitThatActedIsIllegalState(t *testing.T) {
	replies := serve(t, New(openBoard), twoSidesLine,
		standby("a", firstAllyID), standby("b", firstAllyID))
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[2])
	}
}

func TestAnAttackAndItsResponseAttackTravelTogether(t *testing.T) {
	for name, payload := range map[string]string{
		"a response attack alone": `{"actor_id":0,"response_attack":{"stance":"none"}}`,
		"an attack alone":         `{"actor_id":0,"attack":{"weapon_id":0,"target_id":2}}`,
	} {
		t.Run(name, func(t *testing.T) {
			line := `{"id":"a","cmd":"act","payload":` + payload + `}`
			replies := serve(t, New(openBoard), twoSidesLine, line)
			if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
				t.Fatalf("reply: %+v", replies[1])
			}
		})
	}
}

func TestAStanceOutsideTheContractIsBadRequest(t *testing.T) {
	line := `{"id":"a","cmd":"act","payload":{"actor_id":0,"attack":{"weapon_id":0,"target_id":2},` +
		`"response_attack":{"stance":"shield"}}}`
	replies := serve(t, New(openBoard), twoSidesLine, line)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestARefusalLeavesTheBoardAndTheHistory(t *testing.T) {
	replies := serve(t, New(openBoard), twoSidesLine,
		standby("a", enemyID),
		`{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[2].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if len(export.History) != 0 || export.State.Phase != battle.FactionAlly || export.Seed != 5 {
		t.Fatalf("export after a refusal: %+v", export)
	}
}

func TestExportCarriesTheHistoryOfTheActivations(t *testing.T) {
	replies := serve(t, New(openBoard), twoSidesLine,
		standby("a", firstAllyID),
		`{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[2].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if len(export.History) != 1 || export.History[0].Cmd != "act" {
		t.Fatalf("history: %+v", export.History)
	}
	if len(export.Gone) != 0 {
		t.Fatalf("both sides live, and 'gone' is %+v", export.Gone)
	}
	var unit struct {
		ActorID int `json:"actor_id"`
	}
	if err := json.Unmarshal(export.History[0].Payload, &unit); err != nil || unit.ActorID != firstAllyID {
		t.Fatalf("payload: %s", export.History[0].Payload)
	}
	if !export.State.Units[firstAllyID].Acted || export.State.Units[secondAllyID].Acted {
		t.Fatalf("state: %+v", export.State.Units)
	}
}

func TestABoardCommandTakesALineWithNoPayload(t *testing.T) {
	line := `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
		`"units":[{"faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en_max":100}],` +
		`"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`
	replies := serve(t, New(openBoard), line, `{"id":"x","cmd":"export"}`)
	if replies[1].Error != nil {
		t.Fatalf("export with no payload: %+v", replies[1].Error)
	}
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if export.Seed != 5 {
		t.Fatalf("seed: %+v", export)
	}
}

func TestExportNamesTheSideWithNoLivingUnit(t *testing.T) {
	line := `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
		`"units":[` +
		`{"faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en_max":100},` +
		`{"faction":"enemy","pos":[4,4],"hp":0,"max_hp":100,"en_max":100}` +
		`],"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`
	replies := serve(t, New(openBoard), line, `{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if len(export.Gone) != 1 || export.Gone[0] != battle.FactionEnemy {
		t.Fatalf("gone: %+v", export.Gone)
	}
}

func TestExportEchoesTheEventsOfTheLoadedState(t *testing.T) {
	line := `{"id":"l1","cmd":"load","payload":{"state":{` +
		`"units":[{"faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en_max":100}],` +
		`"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":["reinforce_t2"],"fired_events":["opening"]},"history":[]}}`
	replies := serve(t, New(openBoard), line, `{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(export.State.PendingEvents, []string{"reinforce_t2"}) ||
		!reflect.DeepEqual(export.State.FiredEvents, []string{"opening"}) {
		t.Fatalf("events: %+v %+v", export.State.PendingEvents, export.State.FiredEvents)
	}
}

func TestLoadRefusesAMaximumThatTheStateLeavesAtZero(t *testing.T) {
	line := `{"id":"l1","cmd":"load","payload":{"state":{` +
		`"units":[{"faction":"ally","pos":[1,1],"hp":100,"en_max":100,` +
		`"mech":{"hp":12000,"en":140}}],` +
		`"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`
	replies := serve(t, New(openBoard), line)
	if replies[0].OK {
		t.Fatalf("a maximum of zero loaded: %+v", replies[0])
	}
}

func TestInitOpensTurnOneWithTheEnemies(t *testing.T) {
	line := `{"id":"i","cmd":"init","payload":{"board":{"width":6,"height":5},` +
		`"enemies":[{"faction":"enemy","pos":[4,4],"hp":10,"max_hp":100,"en_max":100}],` +
		`"victory":[{"kind":"destroy_all"}],"events":{},"deploy_cells":[[0,0]],"seed":3}}`
	replies := serve(t, New(openBoard), line, `{"id":"x","cmd":"export","payload":{}}`)
	if !replies[0].OK {
		t.Fatalf("init: %+v", replies[0])
	}
	var opened protocol.InitResponse
	if err := json.Unmarshal(replies[0].Payload, &opened); err != nil {
		t.Fatal(err)
	}
	if opened.Turn != 1 || opened.Phase != "ally" || !opened.DeployOpen {
		t.Fatalf("init answer: %+v", opened)
	}
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if export.Seed != 3 || len(export.State.Units) != 1 {
		t.Fatalf("export: %+v", export)
	}
}

func TestInitWithABadBoardIsBadRequest(t *testing.T) {
	replies := serve(t, New(openBoard), `{"id":"i","cmd":"init","payload":{"board":{"width":0,"height":5},"enemies":[]}}`)
	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestInitWithAUnitOfEnemiesThatIsNoEnemyIsBadRequest(t *testing.T) {
	line := `{"id":"i","cmd":"init","payload":{"board":{"width":6,"height":5},` +
		`"enemies":[{"faction":"ally","pos":[1,1],"hp":10,"max_hp":100,"en_max":100}]}}`
	replies := serve(t, New(openBoard), line)
	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestOneSeedGivesOneBattleThroughTheCommandLoop(t *testing.T) {
	first := serve(t, New(openBoard), armedLine, attack("a", 0, 1, 0), `{"id":"x","cmd":"export","payload":{}}`)
	second := serve(t, New(openBoard), armedLine, attack("a", 0, 1, 0), `{"id":"x","cmd":"export","payload":{}}`)
	if !first[1].OK {
		t.Fatalf("act: %+v", first[1])
	}
	if string(first[2].Payload) != string(second[2].Payload) {
		t.Fatalf("two runs of one seed differ:\n%s\n%s", first[2].Payload, second[2].Payload)
	}
}

func TestARefusedActivationMovesTheDrawNowhere(t *testing.T) {
	first := serve(t, New(openBoard), armedLine, standby("r", 1), attack("a", 0, 1, 0), `{"id":"x","cmd":"export","payload":{}}`)
	if first[1].OK {
		t.Fatalf("act: %+v", first[1])
	}
	second := serve(t, New(openBoard), armedLine, attack("a", 0, 1, 0), `{"id":"x","cmd":"export","payload":{}}`)
	if string(first[3].Payload) != string(second[2].Payload) {
		t.Fatalf("a refused activation moved the draw:\n%s\n%s", first[3].Payload, second[2].Payload)
	}
}

const armedLine = `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
	`"units":[` +
	`{"faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en":10,"en_max":100,"mech":{"move_range":0,` +
	`"weapons":[{"name":"gun","power":1000,"range_min":1,"range_max":2,"accuracy":100},` +
	`{"name":"costly","power":9000,"range_min":1,"range_max":2,"en_cost":80,"accuracy":100}]}},` +
	`{"faction":"enemy","pos":[1,2],"hp":100,"max_hp":100,"en_max":100},` +
	`{"faction":"enemy","pos":[8,8],"hp":100,"max_hp":100,"en_max":100}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[9,9]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func attack(id string, unit, target, weapon int) string {
	return `{"id":"` + id + `","cmd":"act","payload":{"actor_id":` + strconv.Itoa(unit) +
		`,"attack":{"weapon_id":` + strconv.Itoa(weapon) + `,"target_id":` + strconv.Itoa(target) + `},` +
		`"response_attack":{"stance":"none"}}}`
}

func TestARefusedActLeavesTheStateByteIdentical(t *testing.T) {
	const exportLine = `{"id":"x","cmd":"export","payload":{}}`
	fresh := serve(t, New(openBoard), armedLine, exportLine)
	if !fresh[0].OK {
		t.Fatalf("load: %+v", fresh[0])
	}
	refusals := map[string]string{
		"an unpaid weapon":      attack("a", 0, 1, 1),
		"an off-phase unit":     standby("a", 1),
		"an unreachable target": attack("a", 0, 2, 0),
	}
	for name, line := range refusals {
		t.Run(name, func(t *testing.T) {
			replies := serve(t, New(openBoard), armedLine, line, exportLine)
			if replies[1].OK {
				t.Fatalf("the act stands: %+v", replies[1])
			}
			if string(replies[2].Payload) != string(fresh[1].Payload) {
				t.Fatalf("the state moved:\n%s\n%s", replies[2].Payload, fresh[1].Payload)
			}
		})
	}
}
