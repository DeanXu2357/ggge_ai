package server

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// engagementLine loads two units three cells apart, each one with the same beam
// weapon, and one ally with no weapon that waits after the strike. The ally
// side therefore keeps the phase, and the answer shows the board of the same
// phase. The accuracy of the weapon leaves room for both outcomes of a draw.
const engagementLine = `{"id":"l1","cmd":"load","payload":{"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[0,0],"hp":12000,"max_hp":12000,` +
	`"en":140,"en_max":140,"unit_attack":4200,"unit_defense":3900,` +
	`"pilot_attack":220,"pilot_defense":190,"reaction":205,"mobility":310,` +
	`"weapons":[{"name":"beam rifle","power":1800,"range_min":1,"range_max":3,` +
	`"en_cost":10,"accuracy":70,"can_counter":true,"usable_after_move":true}]},` +
	`{"unit_id":"a2","faction":"ally","pos":[1,0],"hp":12000,"max_hp":12000},` +
	`{"unit_id":"e1","faction":"enemy","pos":[3,0],"hp":12000,"max_hp":12000,` +
	`"en":140,"en_max":140,"unit_attack":4200,"unit_defense":3900,` +
	`"pilot_attack":220,"pilot_defense":190,"reaction":205,"mobility":310,` +
	`"weapons":[{"name":"beam rifle","power":1800,"range_min":1,"range_max":3,` +
	`"en_cost":10,"accuracy":70,"can_counter":true,"usable_after_move":true}]}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[6,6]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func actLine(id string, action string, reaction string, dice string) string {
	out := `{"id":"` + id + `","cmd":"act","payload":{"unit_id":"a1","action":` + action
	if reaction != "" {
		out += `,"reaction":` + reaction
	}
	return out + `,"dice":` + dice + `}}`
}

const strikeAction = `{"unit_id":"a1","kind":"attack","target_id":"e1","weapon":"beam rifle"}`

const dodge = `{"stance":"dodge","weapon":null,"support_defend":false,"support_attack":true}`

func actResponse(t *testing.T, one reply) protocol.ActResponse {
	t.Helper()
	if !one.OK {
		t.Fatalf("act: %+v", one.Error)
	}
	var payload protocol.ActResponse
	if err := json.Unmarshal(one.Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	return payload
}

func TestActWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), actLine("a1", strikeAction, dodge, `{"mode":"sampled"}`))

	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestActRunsTheStrikeAndAnswersTheResolution(t *testing.T) {
	replies := serve(t, New(), engagementLine,
		actLine("s1", strikeAction, dodge, `{"mode":"forced","outcomes":["hit"]}`),
		`{"id":"x1","cmd":"export","payload":{}}`)

	payload := actResponse(t, replies[1])
	if len(payload.Events) != 1 {
		t.Fatalf("events: %v", payload.Events)
	}
	if payload.Board.Phase != protocol.FactionAlly || payload.Board.Turn != 1 {
		t.Fatalf("board: %+v", payload.Board)
	}
	var snapshot protocol.ExportResponse
	if err := json.Unmarshal(replies[2].Payload, &snapshot); err != nil {
		t.Fatalf("export: %v", err)
	}
	for _, unit := range snapshot.State.Units {
		if unit.UnitID == "e1" && unit.HP >= unit.MaxHP {
			t.Fatalf("the strike took no hit points: %d", unit.HP)
		}
		if unit.UnitID == "a1" && !unit.Acted {
			t.Fatal("the activation did not end")
		}
	}
}

func TestActRefusesAStrikeWithNoReactionOfTheDefender(t *testing.T) {
	replies := serve(t, New(), engagementLine,
		actLine("s1", strikeAction, "", `{"mode":"forced","outcomes":["hit"]}`))

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
	if !strings.Contains(replies[1].Error.Message, "reaction") {
		t.Fatalf("message: %s", replies[1].Error.Message)
	}
}

func TestActRefusesAReactionThatTheStrikePermitsNot(t *testing.T) {
	standby := `{"unit_id":"a1","kind":"standby"}`

	replies := serve(t, New(), engagementLine,
		actLine("s1", standby, dodge, `{"mode":"forced","outcomes":[]}`))

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActRefusesAShortOutcomeListAndKeepsTheBoard(t *testing.T) {
	replies := serve(t, New(), engagementLine,
		actLine("s1", strikeAction, dodge, `{"mode":"forced","outcomes":[]}`),
		`{"id":"x1","cmd":"export","payload":{}}`)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
	var snapshot protocol.ExportResponse
	if err := json.Unmarshal(replies[2].Payload, &snapshot); err != nil {
		t.Fatalf("export: %v", err)
	}
	for _, unit := range snapshot.State.Units {
		if unit.HP != unit.MaxHP || unit.Acted {
			t.Fatalf("the refused activation reached the board: %+v", unit)
		}
	}
}

func TestActRefusesAUnitOfAnotherPhase(t *testing.T) {
	line := `{"id":"s1","cmd":"act","payload":{"unit_id":"e1","action":` +
		`{"unit_id":"e1","kind":"standby"},"dice":{"mode":"forced","outcomes":[]}}}`

	replies := serve(t, New(), engagementLine, line)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActRefusesAnOutcomeOutsideTheContract(t *testing.T) {
	replies := serve(t, New(), engagementLine,
		actLine("s1", strikeAction, dodge, `{"mode":"forced","outcomes":["graze"]}`))

	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActRefusesADiceModeOutsideTheContract(t *testing.T) {
	replies := serve(t, New(), engagementLine,
		actLine("s1", strikeAction, dodge, `{"mode":"enumerate"}`))

	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestActRefusesAnActionOfAnotherUnitThanTheRequest(t *testing.T) {
	line := `{"id":"s1","cmd":"act","payload":{"unit_id":"a1","action":` +
		`{"unit_id":"a2","kind":"standby"},"dice":{"mode":"forced","outcomes":[]}}}`

	replies := serve(t, New(), engagementLine, line)

	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

// exchange plays the board until one side is gone: each unit that waits takes
// the first action of its list, with the last reaction that the strike permits.
// The answer is the whole exchange, one line for each response.
//
// The victory conditions of the stage belong to the issue that reads them, so
// the driver of this test holds the end of the battle, and the engine does not.
func exchange(t *testing.T, seed string) []string {
	t.Helper()
	engine := New()
	log := []string{ask(t, engine, strings.Replace(engagementLine,
		`"history":[]`, `"history":[],"seed":`+seed, 1))}
	for step := 0; step < 200; step++ {
		unit := firstPending(t, engine)
		if unit == "" || wipedOut(t, engine) {
			return log
		}
		action := firstAction(t, engine, unit)
		line := `{"id":"s","cmd":"act","payload":{"unit_id":"` + unit + `","action":` +
			string(action) + reactionField(t, engine, unit, action) +
			`,"dice":{"mode":"sampled"}}}`
		log = append(log, ask(t, engine, line))
	}
	t.Fatal("the battle ran past 200 activations")
	return nil
}

// wipedOut reports whether one side holds no living unit.
func wipedOut(t *testing.T, engine *Server) bool {
	t.Helper()
	var payload protocol.ExportResponse
	unmarshal(t, engine.dispatch([]byte(`{"id":"x","cmd":"export","payload":{}}`)), &payload)
	living := map[protocol.Faction]int{}
	for _, unit := range payload.State.Units {
		if unit.HP > 0 {
			living[unit.Faction]++
		}
	}
	return living[protocol.FactionAlly] == 0 || living[protocol.FactionEnemy] == 0
}

func ask(t *testing.T, engine *Server, line string) string {
	t.Helper()
	answer, err := json.Marshal(engine.dispatch([]byte(line)))
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return string(answer)
}

func firstPending(t *testing.T, engine *Server) string {
	t.Helper()
	var payload protocol.ExportResponse
	unmarshal(t, engine.dispatch([]byte(`{"id":"x","cmd":"export","payload":{}}`)), &payload)
	for _, unit := range payload.State.Units {
		if unit.Faction == payload.State.Phase && unit.HP > 0 && !unit.Acted {
			return unit.UnitID
		}
	}
	return ""
}

func firstAction(t *testing.T, engine *Server, unit string) json.RawMessage {
	t.Helper()
	var payload protocol.ActionsResponse
	unmarshal(t, engine.dispatch([]byte(
		`{"id":"c","cmd":"actions","payload":{"unit_id":"`+unit+`"}}`)), &payload)
	if len(payload.Actions) == 0 {
		t.Fatalf("unit %q holds no action", unit)
	}
	out, err := json.Marshal(payload.Actions[0])
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return out
}

func reactionField(t *testing.T, engine *Server, unit string, action json.RawMessage) string {
	t.Helper()
	var decision protocol.Decision
	if err := json.Unmarshal(action, &decision); err != nil {
		t.Fatalf("action: %v", err)
	}
	if decision.Kind != protocol.ActionAttack || decision.TargetID == nil {
		return ""
	}
	cell := currentCell(t, engine, unit)
	if decision.MoveTo != nil {
		cell = *decision.MoveTo
	}
	request, err := json.Marshal(protocol.ReactionsRequest{
		DefenderID:   *decision.TargetID,
		AttackerID:   unit,
		AttackerCell: cell,
		WeaponID:     *decision.Weapon,
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var payload protocol.ReactionsResponse
	unmarshal(t, engine.dispatch([]byte(
		`{"id":"r","cmd":"reactions","payload":`+string(request)+`}`)), &payload)
	if len(payload.Reactions) == 0 {
		return ""
	}
	chosen, err := json.Marshal(payload.Reactions[len(payload.Reactions)-1])
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return `,"reaction":` + string(chosen)
}

func currentCell(t *testing.T, engine *Server, unit string) protocol.Cell {
	t.Helper()
	var payload protocol.ExportResponse
	unmarshal(t, engine.dispatch([]byte(`{"id":"x","cmd":"export","payload":{}}`)), &payload)
	for _, one := range payload.State.Units {
		if one.UnitID == unit {
			return one.Pos
		}
	}
	t.Fatalf("the board holds no unit %q", unit)
	return protocol.Cell{}
}

func unmarshal(t *testing.T, answer protocol.Response, into any) {
	t.Helper()
	if !answer.OK {
		t.Fatalf("refusal: %+v", answer.Error)
	}
	raw, err := json.Marshal(answer.Payload)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := json.Unmarshal(raw, into); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
}

func TestAWholeBattlePlaysThroughAct(t *testing.T) {
	log := exchange(t, "42")

	if len(log) < 4 {
		t.Fatalf("the battle held %d activations", len(log))
	}
	for _, line := range log {
		if strings.Contains(line, `"ok":false`) {
			t.Fatalf("the engine refused an activation of its own list: %s", line)
		}
	}
}

// The same seed and the same commands give the same battle.
func TestOneSeedGivesOneBattle(t *testing.T) {
	first := exchange(t, "42")
	second := exchange(t, "42")
	other := exchange(t, "43")

	if !reflect.DeepEqual(first, second) {
		t.Fatalf("one seed gave two battles:\n%v\n%v", first, second)
	}
	if reflect.DeepEqual(first, other) {
		t.Fatal("two seeds gave one battle")
	}
}

func TestARefusedActivationDrawsNoDie(t *testing.T) {
	sampled := `{"mode":"sampled"}`
	refused := actLine("bad", strikeAction, "", sampled)
	plain := []string{engagementLine, actLine("s1", strikeAction, dodge, sampled)}
	interrupted := []string{engagementLine, refused, actLine("s1", strikeAction, dodge, sampled)}

	first := serve(t, New(), plain...)
	second := serve(t, New(), interrupted...)

	if string(first[1].Payload) != string(second[2].Payload) {
		t.Fatalf("the refused call moved the source:\n%s\n%s", first[1].Payload, second[2].Payload)
	}
}
