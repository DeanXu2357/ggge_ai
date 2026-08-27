package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// A session holds the board, the seed, and the history of one battle. The
// deploy commands belong to the issue that implements them.
type session struct {
	board       *battle.Board
	victory     []protocol.Victory
	events      json.RawMessage
	deployCells []protocol.Cell
	seed        int64
	draw        *battle.ServerDraw
	history     []protocol.HistoryEntry
}

func newSession(board *battle.Board, seed int64) *session {
	return &session{board: board, seed: seed, draw: battle.NewServerDraw(seed), history: []protocol.HistoryEntry{}}
}

func init() {
	Register("load", func(s *Server) Handler { return s.load })
	Register("reach", func(s *Server) Handler { return s.reach })
	Register("export", func(s *Server) Handler { return s.export })
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
	loaded := newSession(board, request.Seed)
	if request.History != nil {
		loaded.history = request.History
	}
	s.session = loaded
	return protocol.Ok(id, protocol.LoadResponse{})
}

func (s *Server) export(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ExportRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	return protocol.Ok(id, protocol.ExportResponse{
		State:   battle.EncodeState(board),
		History: s.session.history,
		Seed:    s.session.seed,
	})
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
