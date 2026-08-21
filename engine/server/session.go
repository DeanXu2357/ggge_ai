package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// A session holds the board of one battle. 'init', the deploy commands and the
// operation history belong to the issues that implement them; this holder
// carries the board that a geometry command reads.
type session struct {
	board *battle.Board
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

// boardOf gives the board of the session and the request of a command that
// reads the board, or the failure response that the caller answers with. A
// method carries no type parameter, so the server comes in as an argument.
func boardOf[T any](s *Server, id string, payload json.RawMessage,
	into *T) (*battle.Board, *protocol.Response) {
	if s.session == nil {
		fail := protocol.Fail(id, protocol.CodeNoSession, "the engine holds no board")
		return nil, &fail
	}
	if err := decode(payload, into); err != nil {
		fail := protocol.Fail(id, protocol.CodeBadRequest, err.Error())
		return nil, &fail
	}
	return s.session.board, nil
}

func (s *Server) load(id string, payload json.RawMessage) protocol.Response {
	var request protocol.LoadRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeState(&request.State)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	s.session = &session{board: board}
	return protocol.Ok(id, protocol.LoadResponse{})
}

func (s *Server) reach(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ReachRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	cells, err := board.ReachableCells(request.UnitID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, protocol.ReachResponse{Cells: battle.EncodeCells(cells)})
}
