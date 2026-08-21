package battle

import (
	"encoding/json"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func limit(turn int) *int {
	return &turn
}

// scripted gives a board with the ally side done, the enemy side waiting, and
// one event of each trigger kind in the table.
func scripted(events EventTable) *Board {
	state := spent()
	state.Events = events
	for id := range events {
		state.PendingEvents = append(state.PendingEvents, id)
	}
	return state
}

func TestAKillEventFiresWhenItsVictimIsGone(t *testing.T) {
	reinforcement := fighter("e9", FactionEnemy, Cell{4, 0})
	state := scripted(EventTable{"wave_2": {
		ID:      "wave_2",
		Trigger: Trigger{Kind: TriggerKill, UnitID: "e1", WithinTurn: limit(5)},
		Effect:  Effect{Kind: EffectSpawn, Units: []Unit{reinforcement}},
	}})
	state.Phase = FactionEnemy
	state.Unit("e1").HP = 1
	state.Unit("a1").Weapons = []Weapon{beam()}
	state.Unit("a1").Acted = false
	state.Phase = FactionAlly

	resolution, err := state.Act(strikeOf("a1", "e1", "beam rifle"), Forced{Strike: true})
	if err != nil {
		t.Fatalf("act: %v", err)
	}

	if !reflect.DeepEqual(resolution.Fired, []string{"wave_2"}) {
		t.Fatalf("fired: %v", resolution.Fired)
	}
	if state.Unit("e9") == nil {
		t.Fatal("the spawn put no unit on the board")
	}
	if len(state.PendingEvents) != 0 || !reflect.DeepEqual(state.FiredEvents, []string{"wave_2"}) {
		t.Fatalf("pending %v, fired %v", state.PendingEvents, state.FiredEvents)
	}
}

func TestAKillEventPastItsTurnLimitLeavesTheWaitingList(t *testing.T) {
	state := scripted(EventTable{"wave_2": {
		ID:      "wave_2",
		Trigger: Trigger{Kind: TriggerKill, UnitID: "e1", WithinTurn: limit(1)},
		Effect:  Effect{Kind: EffectSpawn},
	}})
	state.Phase = FactionEnemy

	resolution, err := state.Act(Decision{UnitID: "e1", Kind: ActionStandby}, Forced{})
	if err != nil {
		t.Fatalf("act: %v", err)
	}

	if state.Turn != 2 {
		t.Fatalf("turn: %d", state.Turn)
	}
	if len(state.PendingEvents) != 0 || len(state.FiredEvents) != 0 {
		t.Fatalf("pending %v, fired %v", state.PendingEvents, state.FiredEvents)
	}
	for _, rotation := range resolution.Rotations {
		if len(rotation.Fired) != 0 {
			t.Fatalf("an event past its limit fired: %v", rotation.Fired)
		}
	}
}

func TestATurnStartEventFiresOnItsTurn(t *testing.T) {
	state := scripted(EventTable{"boss_weakens": {
		ID:      "boss_weakens",
		Trigger: Trigger{Kind: TriggerTurnStart, Turn: 2},
		Effect: Effect{
			Kind:              EffectWeaken,
			UnitIDs:           []string{"e1"},
			AttackMultiplier:  0.8,
			DefenseMultiplier: 1,
		},
	}})
	state.Phase = FactionEnemy
	before := state.Unit("e1").Mech.Attack

	resolution, err := state.Act(Decision{UnitID: "e1", Kind: ActionStandby}, Forced{})
	if err != nil {
		t.Fatalf("act: %v", err)
	}

	if len(resolution.Rotations) != 1 ||
		!reflect.DeepEqual(resolution.Rotations[0].Fired, []string{"boss_weakens"}) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if got := state.Unit("e1").Mech.Attack; got != before*0.8 {
		t.Fatalf("attack: %v against %v", got, before)
	}
}

func TestASpawnSkipsAnIdentityThatTheBoardHolds(t *testing.T) {
	state := scripted(EventTable{"wave_2": {
		ID:      "wave_2",
		Trigger: Trigger{Kind: TriggerKill, UnitID: "e1"},
		Effect:  Effect{Kind: EffectSpawn, Units: []Unit{fighter("e1", FactionEnemy, Cell{4, 0})}},
	}})
	state.Unit("e1").HP = 0

	state.Act(Decision{UnitID: "a1", Kind: ActionStandby}, Forced{})

	if len(state.Units) != 2 {
		t.Fatalf("units: %d", len(state.Units))
	}
}

func TestAnEventOutsideTheContractStopsTheDecode(t *testing.T) {
	cases := map[string]protocol.StageEvent{
		"an unknown trigger": {
			EventID: "e",
			Trigger: json.RawMessage(`{"type":"rain"}`),
			Effect:  json.RawMessage(`{"type":"spawn"}`),
		},
		"an unknown effect": {
			EventID: "e",
			Trigger: json.RawMessage(`{"type":"kill","uid":"e1"}`),
			Effect:  json.RawMessage(`{"type":"teleport"}`),
		},
	}

	for name, event := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := DecodeEvents(protocol.EventTable{"e": event}); err == nil {
				t.Fatal("the decode took an entry that the turn cycle cannot run")
			}
		})
	}
}

func TestAnAbsentWeakenMultiplierLeavesTheValueAsItWas(t *testing.T) {
	table, err := DecodeEvents(protocol.EventTable{"e": {
		EventID: "e",
		Trigger: json.RawMessage(`{"type":"turn_start","turn":2}`),
		Effect:  json.RawMessage(`{"type":"weaken","uids":["e1"],"attack_multiplier":0.5}`),
	}})
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if got := table["e"].Effect.DefenseMultiplier; got != 1 {
		t.Fatalf("defense multiplier: %v", got)
	}
	if got := table["e"].Effect.AttackMultiplier; got != 0.5 {
		t.Fatalf("attack multiplier: %v", got)
	}
}
