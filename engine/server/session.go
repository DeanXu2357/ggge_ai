package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// A session holds one battle: the board, the stage content that the board does
// not carry, and the random source that a sampled activation draws from. The
// deploy commands belong to the issue that implements them.
type session struct {
	board   *battle.Board
	events  protocol.EventTable
	victory []protocol.Victory
	deploy  []protocol.Cell
	seed    int64
	sampled *battle.Sampled
}

func init() {
	Register("init", func(s *Server) Handler { return s.begin })
	Register("load", func(s *Server) Handler { return s.load })
	Register("export", func(s *Server) Handler { return s.export })
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

// begin builds the battle of the stage. It replaces a live session, and the
// history of the battle starts again.
func (s *Server) begin(id string, payload json.RawMessage) protocol.Response {
	var request protocol.InitRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeInit(&request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	s.session = &session{
		board:   board,
		events:  request.Events,
		victory: request.Victory,
		deploy:  request.DeployCells,
		seed:    request.Seed,
		sampled: battle.NewSampled(request.Seed),
	}
	return protocol.Ok(id, protocol.InitResponse{
		Turn:       board.Turn,
		Phase:      battle.EncodeFaction(board.Phase),
		DeployOpen: true,
	})
}

// load takes the snapshot of a session back. The rules, the event table and the
// seed are optional: a payload that carries none of the three gives the default
// rules, an empty event table and the seed 0.
func (s *Server) load(id string, payload json.RawMessage) protocol.Response {
	var request protocol.LoadRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeState(&request.State)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	if board.Rules, err = battle.DecodeRules(request.Rules); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	if board.Events, err = battle.DecodeEvents(request.Events); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	s.session = &session{
		board:   board,
		events:  request.Events,
		seed:    request.Seed,
		sampled: battle.NewSampled(request.Seed),
	}
	return protocol.Ok(id, protocol.LoadResponse{})
}

// The operation history belongs to the issue that implements 'rollback'. The
// snapshot carries an empty list until then.
func (s *Server) export(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ExportRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	return protocol.Ok(id, protocol.ExportResponse{
		State:   battle.EncodeState(board),
		History: []json.RawMessage{},
		Rules:   battle.EncodeRules(board.Rules),
		Events:  s.session.events,
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
