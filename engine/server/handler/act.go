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
	dice, err := c.openDice(&request.Dice)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	events, err := b.Act(action, dice)
	if err != nil {
		return protocol.Fail(id, refusalCode(err), err.Error())
	}
	c.session.history = append(c.session.history, protocol.HistoryEntry{Cmd: "act", Payload: payload})
	return protocol.Ok(id, protocol.ActResponse{
		Events: events,
		Board:  b.Summary(),
	})
}

func activationOf(request *protocol.ActRequest) (*battle.Decision, error) {
	if request.Action.UnitID != request.UnitID {
		return nil, errors.New("'unit_id' and 'action.unit_id' name two units")
	}
	if request.Action.ResponseAttack != nil {
		return nil, errors.New("the response attack travels in the field 'response_attack' of the request")
	}
	request.Action.ResponseAttack = request.ResponseAttack
	return &request.Action, nil
}

func (c *Commands) openDice(dice *protocol.Dice) (battle.Dice, error) {
	switch dice.Mode {
	case protocol.DiceForced:
		outcomes, err := battle.DecodeOutcomes(dice.Outcomes)
		if err != nil {
			return nil, err
		}
		return battle.NewManualRoll(outcomes), nil
	case protocol.DiceSampled:
		return c.session.draw, nil
	}
	return nil, errors.New("'dice.mode' is not 'forced' or 'sampled'")
}

func refusalCode(err error) string {
	switch {
	case errors.Is(err, battle.ErrOutsideContract):
		return protocol.CodeBadRequest
	case errors.Is(err, battle.ErrOffPhase), errors.Is(err, battle.ErrActed):
		return protocol.CodeIllegalState
	}
	return protocol.CodeIllegalAction
}
