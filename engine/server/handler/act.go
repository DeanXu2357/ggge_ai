package handler

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (c *Commands) Act(id string, payload json.RawMessage) protocol.Response {
	request, b, fail := openCommand[protocol.ActRequest](c, id, payload)
	if fail != nil {
		return *fail
	}
	if (request.Action.Kind == battle.ActionAttack) != (request.ResponseAttack != nil) {
		return protocol.Fail(id, protocol.CodeIllegalAction,
			"the response attack is necessary for an attack and not permitted for every other kind")
	}
	action, err := activationOf(request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	dice, manual, err := c.openDice(&request.Dice)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	// 'Act' is atomic, so the session board resolves the activation itself.
	// A forced roll carries the one refusal that comes after the writes: the
	// list is short only when a draw runs past its end. That path takes a
	// clone.
	target := b
	if manual != nil {
		target = b.Clone()
	}
	events, err := target.Act(action, dice)
	if err != nil {
		return protocol.Fail(id, refusalCode(err), err.Error())
	}
	if manual != nil && manual.Short() {
		return protocol.Fail(id, protocol.CodeIllegalAction, "the 'outcomes' list is short")
	}
	c.session.board = target
	if draw, ok := dice.(*battle.ServerDraw); ok {
		c.session.draw = draw
	}
	c.session.history = append(c.session.history, protocol.HistoryEntry{Cmd: "act", Payload: payload})
	return protocol.Ok(id, protocol.ActResponse{
		Events: events,
		Board:  target.Summary(),
	})
}

func activationOf(request *protocol.ActRequest) (*battle.Decision, error) {
	if request.Action.UnitID == "" {
		request.Action.UnitID = request.UnitID
	}
	if request.Action.UnitID != request.UnitID {
		return nil, errors.New("'unit_id' and 'action.unit_id' name two units")
	}
	if request.Action.ResponseAttack != nil {
		return nil, errors.New("the response attack travels in the field 'response_attack' of the request")
	}
	request.Action.ResponseAttack = request.ResponseAttack
	return &request.Action, nil
}

func (c *Commands) openDice(dice *protocol.Dice) (battle.Dice, *battle.ManualRoll, error) {
	switch dice.Mode {
	case protocol.DiceForced:
		outcomes, err := battle.DecodeOutcomes(dice.Outcomes)
		if err != nil {
			return nil, nil, err
		}
		manual := battle.NewManualRoll(outcomes)
		return manual, manual, nil
	case protocol.DiceSampled:
		return c.session.draw.Clone(), nil, nil
	}
	return nil, nil, errors.New("'dice.mode' is not 'forced' or 'sampled'")
}

func refusalCode(err error) string {
	switch {
	case errors.Is(err, protocol.ErrOutsideContract):
		return protocol.CodeBadRequest
	case errors.Is(err, battle.ErrOffPhase), errors.Is(err, battle.ErrActed):
		return protocol.CodeIllegalState
	}
	return protocol.CodeIllegalAction
}
