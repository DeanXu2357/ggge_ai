package battle

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestEveryEventCarriesItsKindOnTheWire(t *testing.T) {
	result := ActResult{
		Events: []Event{
			MoveEvent{Kind: EventMove, ActorID: 0, From: Cell{1, 1}, To: Cell{2, 1}},
			StrikeEvent{Kind: EventStrike, Segment: SegmentMain, Fired: true, Landed: true,
				Effects: []Effect{{UnitID: 3, HP: &Change[int]{From: 12000, To: 9860}}}},
			ActivationEndEvent{Kind: EventActivationEnd, ActorID: 0,
				Effects: []Effect{{UnitID: 0, Acted: &Change[bool]{From: false, To: true}}}},
			PhaseEvent{Kind: EventPhase, Turn: 1, Phase: FactionEnemy, Effects: []Effect{}},
		},
		Units: []AffectedUnit{},
	}

	out, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}

	for _, want := range []string{
		`{"event":"move","actor_id":0,"from":[1,1],"to":[2,1]}`,
		`"segment":"main"`,
		`"landed":true`,
		`"critical":false`,
		`"effects":[{"unit_id":3,"hp":{"from":12000,"to":9860}}]`,
		`"effects":[{"unit_id":0,"acted":{"from":false,"to":true}}]`,
		`{"event":"phase","turn":1,"phase":"enemy","effects":[]}`,
		`"units":[]`,
	} {
		if !strings.Contains(string(out), want) {
			t.Fatalf("missing %s in\n%s", want, out)
		}
	}
	if strings.Contains(string(out), `"en":`) {
		t.Fatalf("a field that did not change is left out:\n%s", out)
	}
}
