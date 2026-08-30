package protocol

import "encoding/json"

// A chance event is one random node of a resolution. The three consumption
// modes read the same type: enumerate walks every outcome, sampled draws one
// with these probabilities, and forced takes the outcome whose label the
// request names in Dice.Outcomes. The label set of a node belongs to the issue
// that implements the node.
type ChanceEvent struct {
	ID       string          `json:"id"`
	Kind     string          `json:"kind"`
	Outcomes []ChanceOutcome `json:"outcomes"`
}

type ChanceOutcome struct {
	Label       string  `json:"label"`
	Probability float64 `json:"probability"`
}

// StageEvent keeps its trigger and its effect raw: the model holds them as free
// dicts, and the issue that runs the event table reads them.
type StageEvent struct {
	EventID string          `json:"event_id"`
	Trigger json.RawMessage `json:"trigger"`
	Effect  json.RawMessage `json:"effect"`
}

type EventTable = map[string]StageEvent
