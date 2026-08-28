package handler

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (c *Commands) InitBattle(id string, payload json.RawMessage) protocol.Response {
	var request protocol.InitRequest
	if err := json.Unmarshal(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	b, err := board.DecodeInit(&request)
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
