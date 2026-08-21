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
	var request protocol.ActionsRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	if _, err := board.Activatable(request.UnitID); err != nil {
		if errors.Is(err, battle.ErrNoUnit) {
			return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
		}
		return protocol.Fail(id, protocol.CodeIllegalState, err.Error())
	}
	decisions, err := board.Actions(request.UnitID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, protocol.ActionsResponse{Actions: battle.EncodeDecisions(decisions)})
}

func (s *Server) reactions(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ReactionsRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	options, err := board.Reactions(request.DefenderID, request.AttackerID,
		battle.DecodeCell(request.AttackerCell), request.WeaponID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, protocol.ReactionsResponse{Reactions: battle.EncodeReactions(options)})
}
