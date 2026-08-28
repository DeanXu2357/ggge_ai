package server

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("actions", func(s *Server) Handler { return s.actions })
	Register("response_attacks", func(s *Server) Handler { return s.responseAttacks })
}

func (s *Server) actions(id string, payload json.RawMessage) protocol.Response {
	request, b, fail := openCommand[protocol.ActionsRequest](s, id, payload)
	if fail != nil {
		return *fail
	}
	capabilities, err := b.Capabilities(request.UnitID)
	if err != nil {
		if errors.Is(err, battle.ErrNoUnit) {
			return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
		}
		return protocol.Fail(id, protocol.CodeIllegalState, err.Error())
	}
	return protocol.Ok(id, board.EncodeCapabilities(capabilities))
}

func (s *Server) responseAttacks(id string, payload json.RawMessage) protocol.Response {
	request, b, fail := openCommand[protocol.ResponseAttacksRequest](s, id, payload)
	if fail != nil {
		return *fail
	}
	action, err := board.DecodeDecision(&request.Action)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	engagement, err := b.ResponseAttacks(action, request.DefenderID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, board.EncodeEngagement(engagement))
}
