package server

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("actions", func(s *Server) Handler { return s.actions })
	Register("reactions", func(s *Server) Handler { return s.reactions })
}

func (s *Server) actions(id string, payload json.RawMessage) protocol.Response {
	request, board, fail := openCommand[protocol.ActionsRequest](s, id, payload)
	if fail != nil {
		return *fail
	}
	capabilities, err := board.Capabilities(request.UnitID)
	if err != nil {
		if errors.Is(err, battle.ErrNoUnit) {
			return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
		}
		return protocol.Fail(id, protocol.CodeIllegalState, err.Error())
	}
	return protocol.Ok(id, battle.EncodeCapabilities(capabilities))
}

func (s *Server) reactions(id string, payload json.RawMessage) protocol.Response {
	request, board, fail := openCommand[protocol.ReactionsRequest](s, id, payload)
	if fail != nil {
		return *fail
	}
	action, err := battle.DecodeDecision(&request.Action)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	engagement, err := board.Reactions(action, request.DefenderID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, battle.EncodeEngagement(engagement))
}
