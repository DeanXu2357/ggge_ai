package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// A session holds the board, the seed, and the history of one battle. The
// deploy commands belong to the issue that implements them.
type session struct {
	board         *battle.Board
	victory       []protocol.Victory
	events        json.RawMessage
	deployCells   []protocol.Cell
	seed          int64
	draw          *battle.ServerDraw
	history       []protocol.HistoryEntry
	pendingEvents []string
	firedEvents   []string
}

func newSession(board *battle.Board, seed int64) *session {
	return &session{
		board:         board,
		seed:          seed,
		draw:          battle.NewServerDraw(seed),
		history:       []protocol.HistoryEntry{},
		pendingEvents: []string{},
		firedEvents:   []string{},
	}
}

func init() {
	Register("load", func(s *Server) Handler { return s.load })
	Register("reach", func(s *Server) Handler { return s.reach })
	Register("export", func(s *Server) Handler { return s.export })
}

// A command that needs no field arrives with no 'payload', and
// json.Unmarshal refuses empty input. An absent payload gives a zero
// request.
// A method carries no type parameter, so the server comes in as an argument.
func openCommand[T any](s *Server, id string, payload json.RawMessage) (
	*T, *battle.Board, *protocol.Response) {
	var request T
	if s.session == nil {
		fail := protocol.Fail(id, protocol.CodeNoSession, "the engine holds no board")
		return nil, nil, &fail
	}
	if err := json.Unmarshal(payload, &request); err != nil {
		fail := protocol.Fail(id, protocol.CodeBadRequest, err.Error())
		return nil, nil, &fail
	}
	return &request, s.session.board, nil
}

func (s *Server) load(id string, payload json.RawMessage) protocol.Response {
	var request protocol.LoadRequest
	if err := json.Unmarshal(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeState(&request.State)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	// No engine exports a phase that holds no pending unit, but a hand-written
	// snapshot can carry one. The rotation makes such a board playable.
	board.Advance()
	loaded := newSession(board, request.Seed)
	if request.History != nil {
		loaded.history = request.History
	}
	if request.State.PendingEvents != nil {
		loaded.pendingEvents = request.State.PendingEvents
	}
	if request.State.FiredEvents != nil {
		loaded.firedEvents = request.State.FiredEvents
	}
	s.session = loaded
	return protocol.Ok(id, protocol.LoadResponse{})
}

func (s *Server) export(id string, payload json.RawMessage) protocol.Response {
	_, board, fail := openCommand[protocol.ExportRequest](s, id, payload)
	if fail != nil {
		return *fail
	}
	state := battle.EncodeState(board)
	state.PendingEvents = s.session.pendingEvents
	state.FiredEvents = s.session.firedEvents
	return protocol.Ok(id, protocol.ExportResponse{
		State:   state,
		History: s.session.history,
		Seed:    s.session.seed,
		Gone:    battle.EncodeSummary(board).Gone,
	})
}

func (s *Server) reach(id string, payload json.RawMessage) protocol.Response {
	request, board, fail := openCommand[protocol.ReachRequest](s, id, payload)
	if fail != nil {
		return *fail
	}
	cells, err := board.ReachableCells(request.UnitID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, protocol.ReachResponse{Cells: battle.EncodeCells(cells)})
}
