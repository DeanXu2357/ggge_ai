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

type Board struct {
	Width        int           `json:"width"`
	Height       int           `json:"height"`
	Terrain      string        `json:"terrain,omitempty"`
	TerrainCells []TerrainCell `json:"terrain_cells,omitempty"`
}

type HelloRequest struct{}

type PingRequest struct{}

type PingResponse struct{}

type InitRequest struct {
	Board       Board           `json:"board"`
	Enemies     []Unit          `json:"enemies"`
	Victory     []Victory       `json:"victory"`
	Events      json.RawMessage `json:"events,omitempty"`
	DeployCells []Cell          `json:"deploy_cells"`
	Rules       json.RawMessage `json:"rules,omitempty"`
	Seed        int64           `json:"seed"`
}

type InitResponse struct {
	Turn       int    `json:"turn"`
	Phase      string `json:"phase"`
	DeployOpen bool   `json:"deploy_open"`
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
	Unit      UnitStatus    `json:"unit"`
	MoveCells []Cell        `json:"move_cells"`
	Weapons   []WeaponEntry `json:"weapons"`
	Skills    []SkillEntry  `json:"skills"`
	Error     *Error        `json:"error,omitempty"`
}

type UnitStatus struct {
	UnitID    string  `json:"unit_id"`
	Faction   Faction `json:"faction"`
	Pos       Cell    `json:"pos"`
	Size      Cell    `json:"size"`
	HP        int     `json:"hp"`
	MaxHP     int     `json:"max_hp"`
	EN        int     `json:"en"`
	ENMax     int     `json:"en_max"`
	MoveRange int     `json:"move_range"`
	Acted     bool    `json:"acted"`
}

type WeaponEntry struct {
	Name            string  `json:"name"`
	RangeMin        int     `json:"range_min"`
	RangeMax        int     `json:"range_max"`
	ENCost          int     `json:"en_cost"`
	Ammo            *int    `json:"ammo"` // A null 'ammo' is a weapon that spends no ammunition.
	Accuracy        float64 `json:"accuracy"`
	CanCounter      bool    `json:"can_counter"`
	MapWeapon       bool    `json:"map_weapon"`
	UsableAfterMove bool    `json:"usable_after_move"`
}

type SkillEntry struct {
	Kind            SkillKind    `json:"kind"`
	Amount          *float64     `json:"amount"`
	Uses            int          `json:"uses"`
	EndsActivation  bool         `json:"ends_activation"`
	UsableAfterMove bool         `json:"usable_after_move"`
	RangeMin        int          `json:"range_min"`
	RangeMax        int          `json:"range_max"`
	Blast           int          `json:"blast"`
	Affects         SkillAffects `json:"affects"`
}

type ResponseAttacksRequest struct {
	Action     Decision `json:"action"`      // action of the attacker
	DefenderID string   `json:"defender_id"` // target of the attacker
}

type ResponseAttacksResponse struct {
	Defender DefenderOptions `json:"defender"`
	Attacker AttackerOptions `json:"attacker"`
}

type Forecast struct {
	HitRate *float64 `json:"hit_rate"`
	Damage  *float64 `json:"damage"`
	Kill    *bool    `json:"kill"`
}

type ResponseAttackOption struct {
	Stance   Stance    `json:"stance"`
	Weapon   *string   `json:"weapon"`
	Incoming Forecast  `json:"incoming"`
	Counter  *Forecast `json:"counter,omitempty"`
}

type SupportDefendOption struct {
	UnitID   string   `json:"unit_id"`
	Incoming Forecast `json:"incoming"`
}

type SupportAttackOption struct {
	UnitID string   `json:"unit_id"`
	Weapon string   `json:"weapon"`
	Strike Forecast `json:"strike"`
}

type DefenderOptions struct {
	UnitID           string                 `json:"unit_id"`
	ResponseAttacks  []ResponseAttackOption `json:"response_attacks"`
	SupportDefenders []SupportDefendOption  `json:"support_defenders"`
	SupportAttackers []SupportAttackOption  `json:"support_attackers"`
}

type AttackerOptions struct {
	UnitID           string                `json:"unit_id"`
	SupportDefenders []SupportDefendOption `json:"support_defenders"`
	SupportAttackers []SupportAttackOption `json:"support_attackers"`
}

type ActRequest struct {
	UnitID         string          `json:"unit_id"`
	Action         Decision        `json:"action"`
	ResponseAttack *ResponseAttack `json:"response_attack,omitempty"`
	Dice           Dice            `json:"dice"`
}

// An entry of 'events' is a StrikeEvent or a PhaseEvent; the field 'event'
// tells them apart on the wire.
type StrikeEvent struct {
	Event     string `json:"event"`
	Strike    string `json:"strike"`
	ShooterID string `json:"shooter_id"`
	StruckID  string `json:"struck_id"`
	Weapon    string `json:"weapon"`
	Landed    bool   `json:"landed"`
	Damage    int    `json:"damage"`
	Killed    bool   `json:"killed"`
}

type PhaseEvent struct {
	Event string  `json:"event"`
	Turn  int     `json:"turn"`
	Phase Faction `json:"phase"`
}

type BoardSummary struct {
	Turn    int       `json:"turn"`
	Phase   Faction   `json:"phase"`
	Pending []string  `json:"pending"`
	Gone    []Faction `json:"gone"`
}

type ActResponse struct {
	Events []any        `json:"events"`
	Board  BoardSummary `json:"board"`
}

type HistoryEntry struct {
	Cmd     string          `json:"cmd"`
	Payload json.RawMessage `json:"payload"`
}

type Undone = HistoryEntry

type RollbackRequest struct{}

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

type ExportResponse struct {
	State   BattleState    `json:"state"`
	History []HistoryEntry `json:"history"`
	Seed    int64          `json:"seed"`
	Gone    []Faction      `json:"gone"`
}

type LoadRequest struct {
	State   BattleState    `json:"state"`
	History []HistoryEntry `json:"history"`
	Seed    int64          `json:"seed"`
}

type LoadResponse struct{}
