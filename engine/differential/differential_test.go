package differential_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var fixtures = filepath.Join("..", "..", "tests", "fixtures", "engine")

// The three codec ops answer with the value that the case file set up. Every
// other test file of this package adds its own ops from an 'init' that calls
// 'addOps'.
var ops = map[string]differential.Op{
	"state": func(setup *differential.Setup, _ json.RawMessage) (any, error) {
		return setup.State, nil
	},
	"events": func(setup *differential.Setup, _ json.RawMessage) (any, error) {
		return setup.Events, nil
	},
}

func addOps(more map[string]differential.Op) {
	for name, op := range more {
		if _, taken := ops[name]; taken {
			panic("the op " + name + " is registered two times")
		}
		ops[name] = op
	}
}

func load(t *testing.T) []*differential.Case {
	t.Helper()
	paths, err := differential.Files(fixtures)
	if err != nil {
		t.Fatalf("fixtures: %v", err)
	}
	if len(paths) < 4 {
		t.Fatalf("the golden boards are missing: %v", paths)
	}
	cases := make([]*differential.Case, 0, len(paths))
	for _, path := range paths {
		one, err := differential.Load(path)
		if err != nil {
			t.Fatalf("load: %v", err)
		}
		cases = append(cases, one)
	}
	return cases
}

func TestEveryGoldenCaseMatchesThePythonExpectation(t *testing.T) {
	for _, one := range load(t) {
		t.Run(one.Name, func(t *testing.T) {
			result := differential.Run(one, ops)
			for _, err := range result.Errs {
				t.Error(err)
			}
			if len(result.Ran) == 0 {
				t.Fatalf("no check ran; skipped %v", result.Skipped)
			}
			if len(result.Skipped) != 0 {
				t.Logf("skipped ops: %v", result.Skipped)
			}
		})
	}
}

func TestTheGoldenStateEncodingIsStable(t *testing.T) {
	for _, one := range load(t) {
		t.Run(one.Name, func(t *testing.T) {
			state, err := json.Marshal(one.Setup.State)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			if err := differential.Stable[battle.BattleState](state); err != nil {
				t.Error(err)
			}
			events, err := json.Marshal(one.Setup.Events)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			if err := differential.Stable[protocol.EventTable](events); err != nil {
				t.Error(err)
			}
		})
	}
}

func TestAnUnknownOpIsSkippedAndNotAFailure(t *testing.T) {
	one := &differential.Case{
		Name:   "future",
		Checks: []differential.Check{{Op: "reach", Expect: json.RawMessage(`{}`)}},
	}

	result := differential.Run(one, ops)

	if len(result.Errs) != 0 || len(result.Ran) != 0 {
		t.Fatalf("result: %+v", result)
	}
	if len(result.Skipped) != 1 || result.Skipped[0] != "reach" {
		t.Fatalf("skipped: %v", result.Skipped)
	}
}

func TestAFieldOutsideTheGoStructStopsTheLoad(t *testing.T) {
	path := filepath.Join(t.TempDir(), "extra.json")
	body := `{"name":"extra","setup":{"state":{"turn":1,"morale":7}},"checks":[]}`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write: %v", err)
	}

	if _, err := differential.Load(path); err == nil {
		t.Fatal("a field that the Go struct does not hold must stop the load")
	}
}

func TestCompareJSONReadsAFloatWithTheTolerance(t *testing.T) {
	near := differential.CompareJSON(
		[]byte(`{"p":0.30000000000000004}`), []byte(`{"p":0.3}`))
	far := differential.CompareJSON([]byte(`{"p":0.3}`), []byte(`{"p":0.30001}`))
	integer := differential.CompareJSON([]byte(`{"hp":1200}`), []byte(`{"hp":1201}`))

	if near != nil {
		t.Errorf("the last bits of one double must compare equal: %v", near)
	}
	if far == nil || integer == nil {
		t.Errorf("a real difference must fail: %v, %v", far, integer)
	}
}

func TestCompareJSONNamesTheFieldThatDiffers(t *testing.T) {
	err := differential.CompareJSON(
		[]byte(`{"units":[{"hp":10}]}`), []byte(`{"units":[{"hp":9}]}`))

	if err == nil || err.Error() != "units[0].hp: expected 10, got 9" {
		t.Fatalf("error: %v", err)
	}
}
