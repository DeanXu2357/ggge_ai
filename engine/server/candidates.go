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
	if s.session == nil {
		return protocol.Fail(id, protocol.CodeNoSession, "the engine holds no board")
	}
	var request protocol.ActionsRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	decisions, err := s.session.board.Actions(request.UnitID)
	if err != nil {
		if errors.Is(err, battle.ErrNoUnit) {
			return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
		}
		return protocol.Fail(id, protocol.CodeIllegalState, err.Error())
	}
	return protocol.Ok(id, protocol.ActionsResponse{Actions: battle.EncodeDecisions(decisions)})
}

func (s *Server) reactions(id string, payload json.RawMessage) protocol.Response {
	if s.session == nil {
		return protocol.Fail(id, protocol.CodeNoSession, "the engine holds no board")
	}
	var request protocol.ReactionsRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	options, err := s.session.board.Reactions(request.DefenderID, request.AttackerID,
		battle.DecodeCell(request.AttackerCell), request.WeaponID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, protocol.ReactionsResponse{Reactions: battle.EncodeReactions(options)})
}
