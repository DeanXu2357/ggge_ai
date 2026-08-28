package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("init", func(s *Server) Handler { return s.initBattle })
}

func (s *Server) initBattle(id string, payload json.RawMessage) protocol.Response {
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
	s.session = opened
	return protocol.Ok(id, protocol.InitResponse{
		Turn:       b.Turn(),
		Phase:      string(board.EncodeFaction(b.Phase())),
		DeployOpen: true,
	})
}
