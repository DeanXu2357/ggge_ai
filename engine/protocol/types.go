package protocol

import "encoding/json"

type Cell [2]int

type Guarantee string

const (
	GuaranteeKill Guarantee = "kill"
	GuaranteeNone Guarantee = "none"
)

type VictoryKind string

const (
	VictoryDestroyAll    VictoryKind = "destroy_all"
	VictoryDestroyTarget VictoryKind = "destroy_target"
	VictoryReachCell     VictoryKind = "reach_cell"
)

type DiceMode string

const (
	DiceForced  DiceMode = "forced"
	DiceSampled DiceMode = "sampled"
)

type Victory struct {
	Kind     VictoryKind `json:"kind"`
	TargetID string      `json:"target_id,omitempty"`
	Cell     *Cell       `json:"cell,omitempty"`
}

type Score struct {
	SurviveAll bool `json:"survive_all"`
	HPFloor    int  `json:"hp_floor"`
}

type Goal struct {
	Victory []Victory `json:"victory"`
	Score   Score     `json:"score"`
}

type Budget struct {
	TimeMS int `json:"time_ms"`
	Nodes  int `json:"nodes"`
}

type Dice struct {
	Mode     DiceMode `json:"mode"`
	Outcomes []string `json:"outcomes,omitempty"`
}

type Verdict struct {
	// The advisor issue lands the shape of the field: one decision, or the
	// chosen sequence of one turn.
	Action        json.RawMessage `json:"action"`
	ExpectedValue float64         `json:"expected_value"`
	Guarantee     Guarantee       `json:"guarantee"`
	Diagnostics   map[string]any  `json:"diagnostics,omitempty"`
}

// Board is the map that 'init' builds. The terrain of each cell arrives with
// the board, in the two fields that the state carries (user ruling 2026-08-21).
type Board struct {
	Width        int           `json:"width"`
	Height       int           `json:"height"`
	Terrain      string        `json:"terrain,omitempty"`
	TerrainCells []TerrainCell `json:"terrain_cells,omitempty"`
}

// A BoardSummary is what one board looks like after a command that changed it:
// the turn, the side that acts, and the units of that side that still wait.
type BoardSummary struct {
	Turn    int      `json:"turn"`
	Phase   Faction  `json:"phase"`
	Pending []string `json:"pending"`
}

// A StrikeEvent is one shot of one resolution. The field 'kind' names the place
// of the shot in the order of the engagement.
type StrikeEvent struct {
	Kind      string `json:"kind"`
	ShooterID string `json:"shooter_id"`
	StruckID  string `json:"struck_id"`
	Weapon    string `json:"weapon"`
	Landed    bool   `json:"landed"`
	Damage    int    `json:"damage"`
	Killed    bool   `json:"killed"`
}

// A StageEventFired names one stage event that the outcome of the activation
// fired.
type StageEventFired struct {
	Kind    string `json:"kind"`
	EventID string `json:"event_id"`
}

// A PhaseEvent is one phase boundary that the turn cycle crossed.
type PhaseEvent struct {
	Kind  string  `json:"kind"`
	Turn  int     `json:"turn"`
	Phase Faction `json:"phase"`
}

const (
	EventStageEvent = "stage_event"
	EventPhase      = "phase"
)

// The label of one outcome of a chance node. The nodes of an engagement settle
// a shot, so the two labels name a shot that lands and a shot that misses.
const (
	OutcomeHit  = "hit"
	OutcomeMiss = "miss"
)

type HelloRequest struct{}

type PingRequest struct{}

type PingResponse struct{}

type InitRequest struct {
	Board       Board      `json:"board"`
	Enemies     []Unit     `json:"enemies"`
	Victory     []Victory  `json:"victory"`
	Events      EventTable `json:"events,omitempty"`
	DeployCells []Cell     `json:"deploy_cells"`
	Rules       *Rules     `json:"rules,omitempty"`
	Seed        int64      `json:"seed"`
}

type InitResponse struct {
	Turn       int     `json:"turn"`
	Phase      Faction `json:"phase"`
	DeployOpen bool    `json:"deploy_open"`
}

type DeployCellsRequest struct{}

type DeployCellsResponse struct {
	Cells []Cell `json:"cells"`
}

type PlaceRequest struct {
	Unit Unit `json:"unit"`
	Cell Cell `json:"cell"`
}

type PlaceResponse struct {
	Placed []string `json:"placed"`
	Cells  []Cell   `json:"cells"`
}

type RosterRequest struct{}

type RosterResponse struct {
	Units []Unit `json:"units"`
}

type ReachRequest struct {
	UnitID string `json:"unit_id"`
}

type ReachResponse struct {
	Cells []Cell `json:"cells"`
}

type ActionsRequest struct {
	UnitID string `json:"unit_id"`
}

type ActionsResponse struct {
	Actions []Decision `json:"actions"`
}

type ReactionsRequest struct {
	DefenderID   string `json:"defender_id"`
	AttackerID   string `json:"attacker_id"`
	AttackerCell Cell   `json:"attacker_cell"`
	WeaponID     string `json:"weapon_id"`
}

type ReactionsResponse struct {
	Reactions []Reaction `json:"reactions"`
}

type ActRequest struct {
	UnitID   string    `json:"unit_id"`
	Action   Decision  `json:"action"`
	Reaction *Reaction `json:"reaction,omitempty"`
	Dice     Dice      `json:"dice"`
}

// ActResponse holds the resolution in order. One entry is a StrikeEvent, a
// StageEventFired or a PhaseEvent, and its field 'kind' says which.
type ActResponse struct {
	Events []any        `json:"events"`
	Board  BoardSummary `json:"board"`
}

type RollbackRequest struct{}

type Undone struct {
	Cmd     string          `json:"cmd"`
	Payload json.RawMessage `json:"payload"`
}

type RollbackResponse struct {
	Undone Undone          `json:"undone"`
	Board  json.RawMessage `json:"board"`
}

type SetUnitRequest struct {
	UnitID string          `json:"unit_id"`
	Fields json.RawMessage `json:"fields"`
}

type SetUnitResponse struct {
	Unit Unit `json:"unit"`
}

type AdviceRequest struct {
	Faction string `json:"faction"`
	Budget  Budget `json:"budget"`
	Algo    string `json:"algo"`
	Goal    *Goal  `json:"goal,omitempty"`
}

type AdviceResponse = Verdict

type CertifyRequest struct {
	Action Decision `json:"action"`
}

type CertifyResponse struct {
	Guarantee Guarantee `json:"guarantee"`
}

type ExportRequest struct{}

// The snapshot of the session carries the rules, the event table and the seed
// beside the state: without the three, 'load' builds a session that answers
// other numbers than the one that 'export' read.
type ExportResponse struct {
	State   BattleState       `json:"state"`
	History []json.RawMessage `json:"history"`
	Rules   Rules             `json:"rules"`
	Events  EventTable        `json:"events"`
	Seed    int64             `json:"seed"`
}

type LoadRequest struct {
	State   BattleState       `json:"state"`
	History []json.RawMessage `json:"history"`
	Rules   *Rules            `json:"rules,omitempty"`
	Events  EventTable        `json:"events,omitempty"`
	Seed    int64             `json:"seed,omitempty"`
}

type LoadResponse struct{}
