// Package differential runs the golden cases under tests/fixtures/engine. The
// files hold the board, the inputs and the expected outputs, and a Go test
// reads each file and compares its own answers against them.
//
// The Python side wrote these files while it still held the rules of the
// battle. It does not any more (issue #73), and no process writes them again:
// they are frozen. Delete a case that the engine must not keep. Never
// regenerate one.
package differential

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// The frozen files carry a rules block. The contract holds none: every rule of
// the mechanism is a constant of 'engine/battle' (user ruling 2026-08-26). The
// struct stays so the files still load, and no test reads a field of it.
type Rules struct {
	DefendMultiplier        float64 `json:"defend_multiplier"`
	ShieldMultiplier        float64 `json:"shield_multiplier"`
	SupportDefendMultiplier float64 `json:"support_defend_multiplier"`
	DodgeHitPenalty         float64 `json:"dodge_hit_penalty"`
	MaxSupportAttackers     int     `json:"max_support_attackers"`
	ENRegenFraction         float64 `json:"en_regen_fraction"`
	Terrain                 float64 `json:"terrain"`
}

type Setup struct {
	Rules  Rules                `json:"rules"`
	Events protocol.EventTable  `json:"events"`
	State  protocol.BattleState `json:"state"`
}

type Check struct {
	Op     string          `json:"op"`
	Input  json.RawMessage `json:"input"`
	Expect json.RawMessage `json:"expect"`
}

type Case struct {
	Name   string  `json:"name"`
	Note   string  `json:"note"`
	Setup  Setup   `json:"setup"`
	Checks []Check `json:"checks"`
}

// An Op answers one check of a case. A port issue adds its command to the map
// that its test passes to Run; an op that no build implements is skipped, so
// the Python side can write the checks of a later issue today.
type Op func(setup *Setup, input json.RawMessage) (any, error)

type Result struct {
	Ran     []string
	Skipped []string
	Errs    []error
}

// Load reads one case file. An unknown field is an error: a field that the
// Python state holds and the Go struct does not must stop the test, not drop
// out of the answer.
func Load(path string) (*Case, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	decoder := json.NewDecoder(file)
	decoder.DisallowUnknownFields()
	var one Case
	if err := decoder.Decode(&one); err != nil {
		return nil, fmt.Errorf("%s: %w", filepath.Base(path), err)
	}
	return &one, nil
}

func Files(dir string) ([]string, error) {
	paths, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		return nil, err
	}
	sort.Strings(paths)
	return paths, nil
}

func Run(one *Case, ops map[string]Op) Result {
	var result Result
	for index, check := range one.Checks {
		op, known := ops[check.Op]
		if !known {
			result.Skipped = append(result.Skipped, check.Op)
			continue
		}
		result.Ran = append(result.Ran, check.Op)
		answer, err := op(&one.Setup, check.Input)
		if err != nil {
			result.Errs = append(result.Errs, fmt.Errorf("%s[%d] %s: %w",
				one.Name, index, check.Op, err))
			continue
		}
		actual, err := json.Marshal(answer)
		if err != nil {
			result.Errs = append(result.Errs, fmt.Errorf("%s[%d] %s: %w",
				one.Name, index, check.Op, err))
			continue
		}
		if err := CompareJSON(check.Expect, actual); err != nil {
			result.Errs = append(result.Errs, fmt.Errorf("%s[%d] %s: %w",
				one.Name, index, check.Op, err))
		}
	}
	return result
}

// Stable reports whether a decode and an encode of the payload give the same
// bytes a second time.
func Stable[T any](payload []byte) error {
	first, err := reencode[T](payload)
	if err != nil {
		return err
	}
	second, err := reencode[T](first)
	if err != nil {
		return err
	}
	if !bytes.Equal(first, second) {
		return fmt.Errorf("the second encoding differs:\n%s\n%s", first, second)
	}
	return nil
}

func reencode[T any](payload []byte) ([]byte, error) {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var into T
	if err := decoder.Decode(&into); err != nil {
		return nil, err
	}
	return json.Marshal(into)
}
