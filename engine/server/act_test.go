package server

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const twoSidesLine = `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en":100,"en_max":140,"mech":{"move_range":1}},` +
	`{"unit_id":"a2","faction":"ally","pos":[1,2],"hp":100,"max_hp":100,"en":100,"en_max":140,"mech":{"move_range":1}},` +
	`{"unit_id":"e1","faction":"enemy","pos":[4,4],"hp":100,"max_hp":100,"en":100,"en_max":140}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func act(id, unit, kind, dice string) string {
	return `{"id":"` + id + `","cmd":"act","payload":{"unit_id":"` + unit + `","action":{"unit_id":"` + unit +
		`","kind":"` + kind + `"},"dice":` + dice + `}}`
}

func TestActWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), act("a", "a1", "standby", `{"mode":"sampled"}`))
	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestAStandbyAnswersNoEventAndThePendingSibling(t *testing.T) {
	replies := serve(t, New(), twoSidesLine, act("a", "a1", "standby", `{"mode":"sampled"}`))
	if !replies[1].OK {
		t.Fatalf("act: %+v", replies[1])
	}
	var answer struct {
		Events []json.RawMessage   `json:"events"`
		Board  battle.BoardSummary `json:"board"`
	}
	if err := json.Unmarshal(replies[1].Payload, &answer); err != nil {
		t.Fatal(err)
	}
	if len(answer.Events) != 0 || answer.Board.Turn != 1 || answer.Board.Phase != battle.FactionAlly {
		t.Fatalf("answer: %+v", answer)
	}
	if len(answer.Board.Pending) != 1 || answer.Board.Pending[0] != "a2" || len(answer.Board.Gone) != 0 {
		t.Fatalf("summary: %+v", answer.Board)
	}
}

func TestTheLastActivationRotatesAndTheEventsSayWhere(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "a1", "standby", `{"mode":"sampled"}`),
		act("b", "a2", "standby", `{"mode":"sampled"}`))
	var answer struct {
		Events []json.RawMessage   `json:"events"`
		Board  battle.BoardSummary `json:"board"`
	}
	if err := json.Unmarshal(replies[2].Payload, &answer); err != nil {
		t.Fatal(err)
	}
	if answer.Board.Phase != battle.FactionEnemy || len(answer.Events) != 2 {
		t.Fatalf("answer: %+v", answer)
	}
	if string(answer.Events[1]) != `{"event":"phase","turn":1,"phase":"enemy"}` {
		t.Fatalf("last event: %s", answer.Events[1])
	}
}

func TestAUnitOffPhaseIsIllegalState(t *testing.T) {
	replies := serve(t, New(), twoSidesLine, act("a", "e1", "standby", `{"mode":"sampled"}`))
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAUnitThatActedIsIllegalState(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "a1", "standby", `{"mode":"sampled"}`),
		act("b", "a1", "standby", `{"mode":"sampled"}`))
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[2])
	}
}

func TestAResponseAttackOnAStandbyIsIllegalAction(t *testing.T) {
	line := `{"id":"a","cmd":"act","payload":{"unit_id":"a1","action":{"unit_id":"a1","kind":"standby"},` +
		`"response_attack":{"stance":"none"},"dice":{"mode":"sampled"}}}`
	replies := serve(t, New(), twoSidesLine, line)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAResponseAttackInsideTheActionIsBadRequest(t *testing.T) {
	line := `{"id":"a","cmd":"act","payload":{"unit_id":"a1",` +
		`"action":{"unit_id":"a1","kind":"standby","response_attack":{"stance":"none"}},` +
		`"dice":{"mode":"sampled"}}}`
	replies := serve(t, New(), twoSidesLine, line)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAnAttackWithNoResponseAttackIsIllegalAction(t *testing.T) {
	line := `{"id":"a","cmd":"act","payload":{"unit_id":"a1","action":{"unit_id":"a1","kind":"attack","target_id":"e1","weapon":"gun"},` +
		`"dice":{"mode":"forced","outcomes":["hit"]}}}`
	replies := serve(t, New(), twoSidesLine, line)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAnOutcomeOutsideTheLabelsIsBadRequest(t *testing.T) {
	replies := serve(t, New(), twoSidesLine, act("a", "a1", "standby", `{"mode":"forced","outcomes":["yes"]}`))
	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestARefusalLeavesTheBoardAndTheHistory(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "e1", "standby", `{"mode":"sampled"}`),
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
	replies := serve(t, New(), twoSidesLine,
		act("a", "a1", "standby", `{"mode":"sampled"}`),
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
		UnitID string `json:"unit_id"`
	}
	if err := json.Unmarshal(export.History[0].Payload, &unit); err != nil || unit.UnitID != "a1" {
		t.Fatalf("payload: %s", export.History[0].Payload)
	}
	acted := map[string]bool{}
	for _, one := range export.State.Units {
		acted[one.ID] = one.Acted
	}
	if !acted["a1"] || acted["a2"] {
		t.Fatalf("state: %+v", acted)
	}
}

func TestABoardCommandTakesALineWithNoPayload(t *testing.T) {
	line := `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
		`"units":[{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100}],` +
		`"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`
	replies := serve(t, New(), line, `{"id":"x","cmd":"export"}`)
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
		`{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100},` +
		`{"unit_id":"e1","faction":"enemy","pos":[4,4],"hp":0}` +
		`],"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":[],"fired_events":[]},"history":[]}}`
	replies := serve(t, New(), line, `{"id":"x","cmd":"export","payload":{}}`)
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
		`"units":[{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100}],` +
		`"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
		`"pending_events":["reinforce_t2"],"fired_events":["opening"]},"history":[]}}`
	replies := serve(t, New(), line, `{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(export.State.PendingEvents, []string{"reinforce_t2"}) ||
		!reflect.DeepEqual(export.State.FiredEvents, []string{"opening"}) {
		t.Fatalf("events: %+v %+v", export.State.PendingEvents, export.State.FiredEvents)
	}
}

func TestInitOpensTurnOneWithTheEnemies(t *testing.T) {
	line := `{"id":"i","cmd":"init","payload":{"board":{"width":6,"height":5},` +
		`"enemies":[{"unit_id":"e1","faction":"enemy","pos":[4,4],"hp":10}],` +
		`"victory":[{"kind":"destroy_all"}],"events":{},"deploy_cells":[[0,0]],"seed":3}}`
	replies := serve(t, New(), line, `{"id":"x","cmd":"export","payload":{}}`)
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
	replies := serve(t, New(), `{"id":"i","cmd":"init","payload":{"board":{"width":0,"height":5},"enemies":[]}}`)
	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestOneSeedGivesOneBattleThroughTheCommandLoop(t *testing.T) {
	loadLine, actLine := engagementLines(t, 11)
	first := serve(t, New(), loadLine, actLine, `{"id":"x","cmd":"export","payload":{}}`)
	second := serve(t, New(), loadLine, actLine, `{"id":"x","cmd":"export","payload":{}}`)
	if !first[1].OK {
		t.Fatalf("act: %+v", first[1])
	}
	if string(first[2].Payload) != string(second[2].Payload) {
		t.Fatalf("two runs of one seed differ:\n%s\n%s", first[2].Payload, second[2].Payload)
	}
}

// The change goes through the wire types, not string surgery on the line.
func withForcedEmptyOutcomes(t *testing.T, line string) string {
	t.Helper()
	var request struct {
		ID      string          `json:"id"`
		Cmd     string          `json:"cmd"`
		Payload json.RawMessage `json:"payload"`
	}
	if err := json.Unmarshal([]byte(line), &request); err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(request.Payload, &payload); err != nil {
		t.Fatal(err)
	}
	payload["dice"] = map[string]any{"mode": "forced", "outcomes": []string{}}
	encodedPayload, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	request.Payload = encodedPayload
	out, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	return string(out)
}

func TestAShortOutcomesListIsRefusedAfterTheRun(t *testing.T) {
	loadLine, actLine := engagementLines(t, 11)
	shortAct := withForcedEmptyOutcomes(t, actLine)

	replies := serve(t, New(), loadLine, shortAct, `{"id":"x","cmd":"export","payload":{}}`)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("act: %+v", replies[1])
	}

	fresh := serve(t, New(), loadLine, `{"id":"x","cmd":"export","payload":{}}`)
	if string(replies[2].Payload) != string(fresh[1].Payload) {
		t.Fatalf("export after a refused run differs from a fresh export:\n%s\n%s", replies[2].Payload, fresh[1].Payload)
	}
}

func TestARefusedActivationMovesTheDrawNowhere(t *testing.T) {
	loadLine, actLine := engagementLines(t, 11)
	shortAct := withForcedEmptyOutcomes(t, actLine)

	first := serve(t, New(), loadLine, shortAct, actLine, `{"id":"x","cmd":"export","payload":{}}`)
	if first[1].OK {
		t.Fatalf("act: %+v", first[1])
	}
	second := serve(t, New(), loadLine, actLine, `{"id":"x","cmd":"export","payload":{}}`)
	if string(first[3].Payload) != string(second[2].Payload) {
		t.Fatalf("a refused activation moved the draw:\n%s\n%s", first[3].Payload, second[2].Payload)
	}
}

func engagementLines(t *testing.T, seed int64) (string, string) {
	t.Helper()
	raw, err := os.ReadFile("../../tests/fixtures/engine/engagement_board.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Setup struct {
			State json.RawMessage `json:"state"`
		} `json:"setup"`
		Checks []struct {
			Op    string `json:"op"`
			Input struct {
				Decision map[string]any `json:"decision"`
			} `json:"input"`
		} `json:"checks"`
	}
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	var unitID string
	var action map[string]any
	var responseAttack any
	for _, check := range fixture.Checks {
		if check.Op != "apply" {
			continue
		}
		decision := check.Input.Decision
		if decision["kind"] != "attack" || decision["response_attack"] == nil {
			continue
		}
		unitID, _ = decision["unit_id"].(string)
		responseAttack = decision["response_attack"]
		action = make(map[string]any, len(decision))
		for key, value := range decision {
			action[key] = value
		}
		action["response_attack"] = nil
		break
	}
	if action == nil {
		t.Fatal("the fixture holds no attack check with a response attack")
	}

	loadPayload, err := json.Marshal(map[string]any{"seed": seed, "state": fixture.Setup.State})
	if err != nil {
		t.Fatal(err)
	}
	loadLine, err := json.Marshal(map[string]any{"id": "l1", "cmd": "load", "payload": json.RawMessage(loadPayload)})
	if err != nil {
		t.Fatal(err)
	}

	actPayload, err := json.Marshal(map[string]any{
		"unit_id": unitID, "action": action, "response_attack": responseAttack, "dice": map[string]any{"mode": "sampled"},
	})
	if err != nil {
		t.Fatal(err)
	}
	actLine, err := json.Marshal(map[string]any{"id": "a", "cmd": "act", "payload": json.RawMessage(actPayload)})
	if err != nil {
		t.Fatal(err)
	}
	return string(loadLine), string(actLine)
}

const armedLine = `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en":10,"en_max":100,"mech":{"move_range":0,` +
	`"weapons":[{"name":"gun","power":1000,"range_min":1,"range_max":2,"accuracy":100},` +
	`{"name":"costly","power":9000,"range_min":1,"range_max":2,"en_cost":80,"accuracy":100}]}},` +
	`{"unit_id":"e1","faction":"enemy","pos":[1,2],"hp":100,"max_hp":100},` +
	`{"unit_id":"e2","faction":"enemy","pos":[8,8],"hp":100,"max_hp":100}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[9,9]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func attack(id, unit, target, weapon string) string {
	return `{"id":"` + id + `","cmd":"act","payload":{"unit_id":"` + unit + `","action":{"unit_id":"` + unit +
		`","kind":"attack","target_id":"` + target + `","weapon":"` + weapon + `"},` +
		`"response_attack":{"stance":"none"},"dice":{"mode":"sampled"}}}`
}

func TestARefusedActLeavesTheStateByteIdentical(t *testing.T) {
	const exportLine = `{"id":"x","cmd":"export","payload":{}}`
	fresh := serve(t, New(), armedLine, exportLine)
	if !fresh[0].OK {
		t.Fatalf("load: %+v", fresh[0])
	}
	refusals := map[string]string{
		"an unpaid weapon":      attack("a", "a1", "e1", "costly"),
		"an off-phase unit":     act("a", "e1", "standby", `{"mode":"sampled"}`),
		"an unreachable target": attack("a", "a1", "e2", "gun"),
	}
	for name, line := range refusals {
		t.Run(name, func(t *testing.T) {
			replies := serve(t, New(), armedLine, line, exportLine)
			if replies[1].OK {
				t.Fatalf("the act stands: %+v", replies[1])
			}
			if string(replies[2].Payload) != string(fresh[1].Payload) {
				t.Fatalf("the state moved:\n%s\n%s", replies[2].Payload, fresh[1].Payload)
			}
		})
	}
}
