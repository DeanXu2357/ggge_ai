package server

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("act", func(s *Server) Handler { return s.act })
}

func (s *Server) act(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ActRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	if (request.Action.Kind == protocol.ActionAttack) != (request.Reaction != nil) {
		return protocol.Fail(id, protocol.CodeIllegalAction,
			"the reaction is necessary for an attack and not permitted for every other kind")
	}
	decision, err := activation(&request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	dice, manual, err := s.roll(&request.Dice)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	clone := board.Clone()
	resolution, err := clone.Act(decision, dice)
	if err != nil {
		return protocol.Fail(id, refusalCode(err), err.Error())
	}
	if manual != nil && manual.Short() {
		return protocol.Fail(id, protocol.CodeIllegalAction, "the 'outcomes' list is short")
	}
	s.session.board = clone
	if draw, ok := dice.(*battle.ServerDraw); ok {
		s.session.draw = draw
	}
	s.session.history = append(s.session.history, protocol.HistoryEntry{Cmd: "act", Payload: payload})
	return protocol.Ok(id, protocol.ActResponse{
		Events: battle.EncodeResolution(resolution),
		Board:  battle.EncodeSummary(clone),
	})
}

// The request names the unit two times, on the request and on the action.
// The two must agree; an empty action id takes the request id.
func activation(request *protocol.ActRequest) (battle.Decision, error) {
	if request.Action.UnitID == "" {
		request.Action.UnitID = request.UnitID
	}
	if request.Action.UnitID != request.UnitID {
		return battle.Decision{}, errors.New("'unit_id' and 'action.unit_id' name two units")
	}
	decision, err := battle.DecodeDecision(&request.Action)
	if err != nil {
		return battle.Decision{}, err
	}
	if request.Reaction != nil {
		reaction, err := battle.DecodeReaction(*request.Reaction)
		if err != nil {
			return battle.Decision{}, err
		}
		decision.Reaction = &reaction
	}
	return decision, nil
}

func (s *Server) roll(dice *protocol.Dice) (battle.Dice, *battle.ManualRoll, error) {
	switch dice.Mode {
	case protocol.DiceForced:
		outcomes, err := battle.DecodeOutcomes(dice.Outcomes)
		if err != nil {
			return nil, nil, err
		}
		manual := battle.NewManualRoll(outcomes)
		return manual, manual, nil
	case protocol.DiceSampled:
		return s.session.draw.Clone(), nil, nil
	}
	return nil, nil, errors.New("'dice.mode' is not 'forced' or 'sampled'")
}

func refusalCode(err error) string {
	if errors.Is(err, battle.ErrOffPhase) || errors.Is(err, battle.ErrActed) {
		return protocol.CodeIllegalState
	}
	return protocol.CodeIllegalAction
}
