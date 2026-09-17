package protocol

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

type VictoryKind string

const (
	VictoryDestroyAll    VictoryKind = "destroy_all"
	VictoryDestroyTarget VictoryKind = "destroy_target"
	VictoryReachCell     VictoryKind = "reach_cell"
)

type Victory struct {
	Kind     VictoryKind  `json:"kind"`
	TargetID *int         `json:"target_id,omitempty"`
	Cell     *battle.Cell `json:"cell,omitempty"`
}

type Board struct {
	Width        int                  `json:"width"`
	Height       int                  `json:"height"`
	Terrain      battle.Terrain       `json:"terrain,omitempty"`
	TerrainCells []battle.TerrainCell `json:"terrain_cells,omitempty"`
}

type PingResponse struct{}

type InitRequest struct {
	Board       Board           `json:"board"`
	Enemies     []battle.Unit   `json:"enemies"`
	Victory     []Victory       `json:"victory"`
	Events      json.RawMessage `json:"events,omitempty"`
	DeployCells []battle.Cell   `json:"deploy_cells"`
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
	Cells []battle.Cell `json:"cells"`
}

type PlaceRequest struct {
	Unit battle.Unit `json:"unit"`
	Cell battle.Cell `json:"cell"`
}

type PlaceResponse struct {
	Placed []int         `json:"placed"`
	Cells  []battle.Cell `json:"cells"`
}

type RosterRequest struct{}

type RosterResponse struct {
	Units []battle.Unit `json:"units"`
}

type ReachRequest struct {
	UnitID int `json:"unit_id"`
}

type ReachResponse struct {
	Cells []battle.Cell `json:"cells"`
}

type ActionsRequest struct {
	UnitID int `json:"unit_id"`
}

type ResponseAttacksRequest struct {
	Action     battle.Decision `json:"action"`      // action of the attacker
	DefenderID int             `json:"defender_id"` // target of the attacker
}

type ActRequest = battle.Action

type ActResponse struct {
	Events  []battle.Event        `json:"events"`
	Units   []battle.AffectedUnit `json:"units"`
	Outcome battle.Outcome        `json:"outcome"`
	Board   battle.BoardSummary   `json:"board"`
}

type HistoryEntry struct {
	Cmd     string          `json:"cmd"`
	Payload json.RawMessage `json:"payload"`
}

type ExportRequest struct{}

type ExportResponse struct {
	State   battle.BattleState `json:"state"`
	History []HistoryEntry     `json:"history"`
	Seed    int64              `json:"seed"`
	Gone    []battle.Faction   `json:"gone"`
}

type LoadRequest struct {
	State   battle.BattleState `json:"state"`
	History []HistoryEntry     `json:"history"`
	Seed    int64              `json:"seed"`
}

type LoadResponse struct{}
