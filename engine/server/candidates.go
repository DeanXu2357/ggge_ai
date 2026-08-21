package server

import (
	"encoding/json"
	"fmt"

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
	board := s.session.board
	unit := board.Unit(request.UnitID)
	if unit == nil {
		return protocol.Fail(id, protocol.CodeIllegalAction,
			fmt.Sprintf("the board holds no unit %q", request.UnitID))
	}
	if unit.Faction != board.Phase {
		return protocol.Fail(id, protocol.CodeIllegalState,
			fmt.Sprintf("unit %q is of the side %q, and the phase is %q",
				unit.ID, unit.Faction, board.Phase))
	}
	if unit.Acted {
		return protocol.Fail(id, protocol.CodeIllegalState,
			fmt.Sprintf("unit %q acted in this turn", unit.ID))
	}
	decisions, err := board.Actions(request.UnitID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
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
