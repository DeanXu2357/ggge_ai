package handler

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

type session struct {
	board         battle.Board
	victory       []protocol.Victory
	events        json.RawMessage
	deployCells   []protocol.Cell
	seed          int64
	draw          *battle.ServerDraw
	history       []protocol.HistoryEntry
	pendingEvents []string
	firedEvents   []string
}

func newSession(b battle.Board, seed int64) *session {
	return &session{
		board:         b,
		seed:          seed,
		draw:          battle.NewServerDraw(seed),
		history:       []protocol.HistoryEntry{},
		pendingEvents: []string{},
		firedEvents:   []string{},
	}
}

func openCommand[T any](c *Commands, id string, payload json.RawMessage) (
	*T, battle.Board, *protocol.Response) {
	var request T
	if c.session == nil {
		fail := protocol.Fail(id, protocol.CodeNoSession, "the engine holds no board")
		return nil, nil, &fail
	}
	if err := json.Unmarshal(payload, &request); err != nil {
		fail := protocol.Fail(id, protocol.CodeBadRequest, err.Error())
		return nil, nil, &fail
	}
	return &request, c.session.board, nil
}

func (c *Commands) Load(id string, payload json.RawMessage) protocol.Response {
	var request protocol.LoadRequest
	if err := json.Unmarshal(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	b, err := board.DecodeState(&request.State)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	// No engine exports a phase that holds no pending unit, but a hand-written
	// snapshot can carry one. The rotation makes such a board playable.
	b.Advance()
	loaded := newSession(b, request.Seed)
	if request.History != nil {
		loaded.history = request.History
	}
	if request.State.PendingEvents != nil {
		loaded.pendingEvents = request.State.PendingEvents
	}
	if request.State.FiredEvents != nil {
		loaded.firedEvents = request.State.FiredEvents
	}
	c.session = loaded
	return protocol.Ok(id, protocol.LoadResponse{})
}

func (c *Commands) Export(id string, payload json.RawMessage) protocol.Response {
	_, b, fail := openCommand[protocol.ExportRequest](c, id, payload)
	if fail != nil {
		return *fail
	}
	state := b.State()
	state.PendingEvents = c.session.pendingEvents
	state.FiredEvents = c.session.firedEvents
	return protocol.Ok(id, protocol.ExportResponse{
		State:   state,
		History: c.session.history,
		Seed:    c.session.seed,
		Gone:    b.Summary().Gone,
	})
}

func (c *Commands) Reach(id string, payload json.RawMessage) protocol.Response {
	request, b, fail := openCommand[protocol.ReachRequest](c, id, payload)
	if fail != nil {
		return *fail
	}
	cells, err := b.ReachableCells(request.UnitID)
	if err != nil {
		return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
	}
	return protocol.Ok(id, protocol.ReachResponse{Cells: cells})
}
