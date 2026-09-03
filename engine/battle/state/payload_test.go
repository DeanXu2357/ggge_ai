package state

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

// The loader of issue #92 writes the crew beside the mech and the pilot. The
// crew is outside the contract of the engine, and this test drops it.
type loaderPayload struct {
	Mech  json.RawMessage `json:"mech"`
	Pilot json.RawMessage `json:"pilot"`
	Crew  json.RawMessage `json:"crew"`
}

func gamedataDir() string {
	return filepath.Join("..", "..", "..", "tests", "fixtures", "gamedata")
}

func decodeStrict(data []byte, into any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	return decoder.Decode(into)
}

func readPayload(t *testing.T, name string) loaderPayload {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(gamedataDir(), name))
	if err != nil {
		t.Fatalf("read the payload %s: %v", name, err)
	}
	var payload loaderPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		t.Fatalf("decode the payload %s: %v", name, err)
	}
	return payload
}

func payloadMech(t *testing.T, name string, payload loaderPayload) battle.Mech {
	t.Helper()
	var mech battle.Mech
	if err := decodeStrict(payload.Mech, &mech); err != nil {
		t.Fatalf("decode the mech of %s: %v", name, err)
	}
	return mech
}

func payloadPilot(t *testing.T, name string, payload loaderPayload) battle.Pilot {
	t.Helper()
	var pilot battle.Pilot
	if err := decodeStrict(payload.Pilot, &pilot); err != nil {
		t.Fatalf("decode the pilot of %s: %v", name, err)
	}
	return pilot
}

func TestEveryLoaderPayloadDecodesIntoTheContract(t *testing.T) {
	names, err := filepath.Glob(filepath.Join(gamedataDir(), "*.json"))
	if err != nil {
		t.Fatalf("list the payload directory: %v", err)
	}
	if len(names) == 0 {
		t.Fatalf("no payload in %s", gamedataDir())
	}

	for _, path := range names {
		name := filepath.Base(path)
		t.Run(name, func(t *testing.T) {
			payload := readPayload(t, name)
			mech := fromContractMech(payloadMech(t, name, payload))
			pilot := fromContractPilot(payloadPilot(t, name, payload))

			if mech.HP <= 0 {
				t.Errorf("the mech carries the HP %d", mech.HP)
			}
			if mech.EN <= 0 {
				t.Errorf("the mech carries the EN %d", mech.EN)
			}
			if len(mech.Weapons) == 0 {
				t.Fatalf("the mech carries no weapon")
			}
			if len(mech.MapWeapons) != 0 {
				t.Errorf("the mech carries %d map weapons, and this issue writes none",
					len(mech.MapWeapons))
			}
			for index, weapon := range mech.Weapons {
				if weapon.RangeMin > weapon.RangeMax {
					t.Errorf("the weapon %d (%s) reaches from %d to %d",
						index, weapon.Name, weapon.RangeMin, weapon.RangeMax)
				}
				if weapon.ENCost < 0 {
					t.Errorf("the weapon %d (%s) costs the EN %d",
						index, weapon.Name, weapon.ENCost)
				}
				if weapon.Power <= 0 {
					t.Errorf("the weapon %d (%s) carries the power %g",
						index, weapon.Name, weapon.Power)
				}
				for _, category := range weapon.Categories {
					if !slices.Contains(battle.WeaponCategories[:], category) {
						t.Errorf("the weapon %d (%s) carries the unknown category %q",
							index, weapon.Name, category)
					}
				}
			}
			for label, value := range map[string]float64{
				"ranged": pilot.Ranged, "melee": pilot.Melee, "awaken": pilot.Awaken,
				"defense": pilot.Defense, "reaction": pilot.Reaction,
			} {
				if value < 0 {
					t.Errorf("the pilot carries the %s %g", label, value)
				}
			}
			if pilot.SP < 0 {
				t.Errorf("the pilot carries the SP %d", pilot.SP)
			}
		})
	}
}

func TestTheZeongPayloadCarriesTheSspWeapon(t *testing.T) {
	const name = "zeong_sp_ssp_lb3.json"
	mech := fromContractMech(payloadMech(t, name, readPayload(t, name)))

	if mech.HP != 96479 {
		t.Errorf("the mech carries the HP %d, and the golden carries 96479", mech.HP)
	}
	if len(mech.Weapons) != 4 {
		t.Fatalf("the mech carries %d weapons, and the golden carries 4", len(mech.Weapons))
	}

	ssp := mech.Weapons[len(mech.Weapons)-1]
	if ssp.Name != "All-Range Attack SSP" {
		t.Errorf("the last weapon is %q", ssp.Name)
	}
	if ssp.Power != 5880 {
		t.Errorf("the SSP weapon carries the power %g", ssp.Power)
	}
	if ssp.ENCost != 54 {
		t.Errorf("the SSP weapon costs the EN %d", ssp.ENCost)
	}
	if ssp.RangeMin != 2 || ssp.RangeMax != 5 {
		t.Errorf("the SSP weapon reaches from %d to %d", ssp.RangeMin, ssp.RangeMax)
	}
	if !slices.Equal(ssp.Categories, []battle.WeaponCategory{battle.WeaponCategoryAwaken}) {
		t.Errorf("the SSP weapon carries the categories %v", ssp.Categories)
	}
}

func TestTheZeongExPayloadCarriesTheLimitBreak(t *testing.T) {
	const name = "zeong_ex_lb3.json"
	mech := fromContractMech(payloadMech(t, name, readPayload(t, name)))

	if mech.HP != 100478 {
		t.Errorf("the mech carries the HP %d, and the golden carries 100478", mech.HP)
	}
}

func TestAPayloadKeyTheEngineDoesNotKnowIsRejected(t *testing.T) {
	payload := []byte(`{
		"hp": 1, "en": 1, "attack": 1.0, "defense": 1.0, "mobility": 1.0,
		"move_range": 1, "weapons": [], "map_weapons": [], "crew_bonus": 1
	}`)

	var mech battle.Mech
	if err := decodeStrict(payload, &mech); err == nil {
		t.Errorf("the decoder accepted the key 'crew_bonus' and read %+v", mech)
	}
}
