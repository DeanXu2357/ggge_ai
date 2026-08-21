package server

import (
	"encoding/json"
	"errors"
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("act", func(s *Server) Handler { return s.act })
}

// act runs one activation and the turn cycle after it. The command works on a
// copy of the board and installs the copy when the whole run succeeds, so a
// refusal leaves the session as it was: a short outcome list of the forced dice
// shows up only once the resolution asks for the outcome that is not there.
func (s *Server) act(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ActRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	decision, err := activation(request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	roll, err := s.roll(request.Dice)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	next := board.Clone()
	if err := reactionFits(next, decision); err != nil {
		return refusal(id, err)
	}
	resolution, err := next.Act(decision, roll.dice)
	if err != nil {
		return refusal(id, err)
	}
	if roll.short() {
		return protocol.Fail(id, protocol.CodeIllegalAction,
			"the outcome list of the forced dice holds fewer outcomes than the resolution settles")
	}
	s.session.board = next
	roll.keep(s.session)
	return protocol.Ok(id, protocol.ActResponse{
		Events: battle.EncodeResolution(resolution),
		Board:  battle.EncodeSummary(next),
	})
}

// activation reads the decision of the request. The field 'reaction' of the
// request is the answer of the defender; a reaction inside 'action' applies only
// when the request carries none.
func activation(request protocol.ActRequest) (battle.Decision, error) {
	unitID := request.UnitID
	if unitID == "" {
		unitID = request.Action.UnitID
	}
	if request.Action.UnitID != "" && request.Action.UnitID != unitID {
		return battle.Decision{}, fmt.Errorf(
			"the request names the unit %q and its action names the unit %q",
			request.UnitID, request.Action.UnitID)
	}
	decision, err := battle.DecodeDecision(request.Action)
	if err != nil {
		return battle.Decision{}, err
	}
	decision.UnitID = unitID
	if request.Reaction != nil {
		reaction, err := battle.DecodeReaction(*request.Reaction)
		if err != nil {
			return battle.Decision{}, err
		}
		decision.Reaction = &reaction
	}
	return decision, nil
}

// The contract binds the reaction to the answer of 'reactions': a strike that
// permits one needs one, and a strike that permits none takes none.
func reactionFits(board *battle.Board, decision battle.Decision) error {
	options, err := board.StrikeReactions(decision)
	if err != nil {
		return err
	}
	if len(options) > 0 && decision.Reaction == nil {
		return fmt.Errorf("%w: the strike of unit %q needs the reaction of its defender",
			battle.ErrIllegalAction, decision.UnitID)
	}
	if len(options) == 0 && decision.Reaction != nil {
		return fmt.Errorf("%w: the action of unit %q permits no reaction",
			battle.ErrIllegalAction, decision.UnitID)
	}
	return nil
}

// A roll is the dice of one activation, in the shape that the command reads
// after the run: a scripted roll answers whether the outcome list ran out, and
// a sampled roll goes back into the session.
type roll struct {
	dice     battle.Dice
	scripted *battle.Scripted
	sampled  *battle.Sampled
}

func (r roll) short() bool {
	return r.scripted != nil && r.scripted.Short()
}

func (r roll) keep(one *session) {
	if r.sampled != nil {
		one.sampled = r.sampled
	}
}

// roll reads the dice input. A sampled call draws from a copy of the session
// source, and the command installs the copy when the activation succeeds, so a
// refused activation draws nothing.
func (s *Server) roll(input protocol.Dice) (roll, error) {
	switch input.Mode {
	case protocol.DiceForced:
		outcomes, err := battle.DecodeOutcomes(input.Outcomes)
		if err != nil {
			return roll{}, err
		}
		scripted := battle.NewScripted(outcomes)
		return roll{dice: scripted, scripted: scripted}, nil
	case protocol.DiceSampled:
		if len(input.Outcomes) > 0 {
			return roll{}, fmt.Errorf("a sampled call carries no outcome list")
		}
		sampled := s.session.sampled.Clone()
		return roll{dice: sampled, sampled: sampled}, nil
	}
	return roll{}, fmt.Errorf("the dice mode %q is not in the contract", input.Mode)
}

func refusal(id string, err error) protocol.Response {
	switch {
	case errors.Is(err, battle.ErrDestroyed),
		errors.Is(err, battle.ErrOffPhase),
		errors.Is(err, battle.ErrActed):
		return protocol.Fail(id, protocol.CodeIllegalState, err.Error())
	}
	return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
}
