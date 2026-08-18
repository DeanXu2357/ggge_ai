package server

import (
	"encoding/json"
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// A session holds the board of one battle. 'init', the deploy commands and the
// operation history belong to the issues that implement them; this holder
// carries the board that a geometry command reads.
type session struct {
	state protocol.BattleState
}

func init() {
	Register("load", func(s *Server) Handler { return s.load })
	Register("reach", func(s *Server) Handler { return s.reach })
}

func decode[T any](payload json.RawMessage, into *T) error {
	if len(payload) == 0 {
		return nil
	}
	return json.Unmarshal(payload, into)
}

func (s *Server) load(id string, payload json.RawMessage) protocol.Response {
	var request protocol.LoadRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	s.session = &session{state: request.State}
	return protocol.Ok(id, protocol.LoadResponse{})
}

func (s *Server) reach(id string, payload json.RawMessage) protocol.Response {
	if s.session == nil {
		return protocol.Fail(id, protocol.CodeNoSession, "the engine holds no board")
	}
	var request protocol.ReachRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	unit := battle.Find(&s.session.state, request.UnitID)
	if unit == nil {
		return protocol.Fail(id, protocol.CodeIllegalAction,
			fmt.Sprintf("the board holds no unit %q", request.UnitID))
	}
	cells := battle.SortedCells(battle.ReachableCells(&s.session.state, unit), unit.Pos)
	return protocol.Ok(id, protocol.ReachResponse{Cells: cells})
}
