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
	bounds := battle.Bounds{{0, 0}, {request.Board.Width - 1, request.Board.Height - 1}}
	b, err := c.factory.NewBoard(bounds, request.Board.Terrain, request.Board.TerrainCells, request.Enemies)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	opened := newSession(b, request.Seed)
	opened.victory = request.Victory
	opened.events = request.Events
	opened.deployCells = request.DeployCells
	c.session = opened
	summary := b.Summary()
	return protocol.Ok(id, protocol.InitResponse{
		Turn:       summary.Turn,
		Phase:      string(summary.Phase),
		DeployOpen: true,
	})
}
