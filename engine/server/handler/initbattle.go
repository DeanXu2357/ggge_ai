package handler

import (
	"encoding/json"
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (c *Commands) InitBattle(id string, payload json.RawMessage) protocol.Response {
	var request protocol.InitRequest
	if err := json.Unmarshal(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	if request.Board.Width < 1 || request.Board.Height < 1 {
		return protocol.Fail(id, protocol.CodeBadRequest,
			fmt.Sprintf("the board %dx%d holds no cell", request.Board.Width, request.Board.Height))
	}
	for index := range request.Enemies {
		unit := &request.Enemies[index]
		if unit.Faction != battle.FactionEnemy {
			return protocol.Fail(id, protocol.CodeBadRequest,
				fmt.Sprintf("the unit %d of 'enemies' carries the faction %q",
					index, unit.Faction))
		}
	}
	bounds := battle.Bounds{{0, 0}, {request.Board.Width - 1, request.Board.Height - 1}}
	board := c.open(request.Seed)
	if err := board.Load(bounds, request.Board.Terrain, request.Board.TerrainCells,
		request.Enemies, battle.FactionAlly, 1); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	c.board = board
	opened := newSession(request.Seed)
	opened.victory = request.Victory
	opened.events = request.Events
	opened.deployCells = request.DeployCells
	c.session = opened
	summary := c.board.Summary()
	return protocol.Ok(id, protocol.InitResponse{
		Turn:       summary.Turn,
		Phase:      string(summary.Phase),
		DeployOpen: true,
	})
}
