package protocol

import "encoding/json"

// StageEvent keeps its trigger and its effect raw: the model holds them as free
// dicts, and the issue that runs the event table reads them.
type StageEvent struct {
	EventID string          `json:"event_id"`
	Trigger json.RawMessage `json:"trigger"`
	Effect  json.RawMessage `json:"effect"`
}

type EventTable = map[string]StageEvent
