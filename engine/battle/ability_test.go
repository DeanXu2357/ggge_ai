package battle

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func TestEveryAbilityKindOfTheTableCarriesItsKindAndSurvivesTheRoundTrip(t *testing.T) {
	for kind, zero := range abilityKinds {
		t.Run(string(kind), func(t *testing.T) {
			line := zero()
			if line.Kind() != kind {
				t.Fatalf("the table binds %q to a struct of the kind %q", kind, line.Kind())
			}

			payload, err := json.Marshal(Abilities{line})
			if err != nil {
				t.Fatal(err)
			}
			var back Abilities
			if err := json.Unmarshal(payload, &back); err != nil {
				t.Fatal(err)
			}

			if !reflect.DeepEqual(back, Abilities{line}) {
				t.Fatalf("%s comes back as %+v", payload, back)
			}
		})
	}
}

func TestAnEncodedAbilityOpensWithItsKind(t *testing.T) {
	for kind, zero := range abilityKinds {
		payload, err := encodeAbility(zero())
		if err != nil {
			t.Fatal(err)
		}

		if opening := `{"kind":"` + string(kind) + `"`; !strings.HasPrefix(string(payload), opening) {
			t.Errorf("the kind %q writes %s", kind, payload)
		}
	}
}

func TestAKindOutsideTheTableComesBackAsItCame(t *testing.T) {
	payload := []byte(`[{"kind":"revive_once","count":1,"note":{"why":["a",2]}}]`)

	var lines Abilities
	if err := json.Unmarshal(payload, &lines); err != nil {
		t.Fatal(err)
	}
	back, err := json.Marshal(lines)
	if err != nil {
		t.Fatal(err)
	}

	if len(lines) != 1 || lines[0].Kind() != "revive_once" {
		t.Fatalf("the list reads %+v", lines)
	}
	if string(back) != string(payload) {
		t.Fatalf("the line goes in as %s and comes out as %s", payload, back)
	}
}

func TestAnAbilityListKeepsTheEmptyFormItCameIn(t *testing.T) {
	var empty Abilities
	if err := json.Unmarshal([]byte(`[]`), &empty); err != nil {
		t.Fatal(err)
	}
	emptyBack, err := json.Marshal(empty)
	if err != nil {
		t.Fatal(err)
	}
	absent, err := json.Marshal(Abilities(nil))
	if err != nil {
		t.Fatal(err)
	}

	if string(emptyBack) != "[]" {
		t.Errorf("an empty list writes %s", emptyBack)
	}
	if string(absent) != "null" {
		t.Errorf("a list that no state carries writes %s", absent)
	}
}
