package differential

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
)

// The float comparison rule of the harness.
//
// A number that one side copies from the other matches bit for bit: Python and
// Go both write the shortest decimal that reads back as the same IEEE-754
// double. A number that each side computes does not: the two runtimes call
// different libm code for 'exp', and the results part in the last bits. The
// comparison therefore takes a relative tolerance, with an absolute floor for
// the numbers near zero. The tolerance hides no wrong formula, because a wrong
// formula misses by far more than this, and it hides no wrong integer, because
// the smallest difference between two integers is 1.
const (
	RelativeTolerance = 1e-9
	AbsoluteTolerance = 1e-12
)

// CompareJSON reports the first difference between two JSON documents.
func CompareJSON(expect, actual []byte) error {
	var want, got any
	if err := json.Unmarshal(expect, &want); err != nil {
		return fmt.Errorf("the expectation is not JSON: %w", err)
	}
	if err := json.Unmarshal(actual, &got); err != nil {
		return fmt.Errorf("the answer is not JSON: %w", err)
	}
	return compare("", want, got)
}

func compare(path string, want, got any) error {
	switch wanted := want.(type) {
	case map[string]any:
		return compareObject(path, wanted, got)
	case []any:
		return compareArray(path, wanted, got)
	case float64:
		number, ok := got.(float64)
		if !ok {
			return mismatch(path, want, got)
		}
		if !withinTolerance(wanted, number) {
			return mismatch(path, want, got)
		}
		return nil
	default:
		if want != got {
			return mismatch(path, want, got)
		}
		return nil
	}
}

func compareObject(path string, want map[string]any, got any) error {
	object, ok := got.(map[string]any)
	if !ok {
		return mismatch(path, want, got)
	}
	keys := make([]string, 0, len(want))
	for key := range want {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		value, present := object[key]
		if !present {
			return fmt.Errorf("%s: the answer has no field", join(path, key))
		}
		if err := compare(join(path, key), want[key], value); err != nil {
			return err
		}
	}
	for key := range object {
		if _, present := want[key]; !present {
			return fmt.Errorf("%s: the answer carries a field the expectation does not",
				join(path, key))
		}
	}
	return nil
}

func compareArray(path string, want []any, got any) error {
	list, ok := got.([]any)
	if !ok {
		return mismatch(path, want, got)
	}
	if len(want) != len(list) {
		return fmt.Errorf("%s: length %d against %d", label(path), len(want), len(list))
	}
	for index := range want {
		if err := compare(fmt.Sprintf("%s[%d]", path, index), want[index], list[index]); err != nil {
			return err
		}
	}
	return nil
}

func withinTolerance(want, got float64) bool {
	if want == got {
		return true
	}
	if math.IsNaN(want) || math.IsNaN(got) || math.IsInf(want, 0) || math.IsInf(got, 0) {
		return false
	}
	gap := math.Abs(want - got)
	scale := math.Max(math.Abs(want), math.Abs(got))
	return gap <= AbsoluteTolerance || gap <= RelativeTolerance*scale
}

func mismatch(path string, want, got any) error {
	return fmt.Errorf("%s: expected %v, got %v", label(path), render(want), render(got))
}

func render(value any) string {
	out, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprintf("%v", value)
	}
	return string(out)
}

func join(path, key string) string {
	if path == "" {
		return key
	}
	return path + "." + key
}

func label(path string) string {
	if path == "" {
		return "the document"
	}
	return path
}
