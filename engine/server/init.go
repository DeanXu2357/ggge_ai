package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("init", func(s *Server) Handler { return s.initBattle })
}

func (s *Server) initBattle(id string, payload json.RawMessage) protocol.Response {
	var request protocol.InitRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeInit(&request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	opened := newSession(board, request.Seed)
	opened.victory = request.Victory
	opened.events = request.Events
	opened.deployCells = request.DeployCells
	s.session = opened
	return protocol.Ok(id, protocol.InitResponse{Turn: board.Turn, Phase: string(protocol.FactionAlly), DeployOpen: true})
}
