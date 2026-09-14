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
	result, err := b.Act(request)
	if err != nil {
		return protocol.Fail(id, refusalCode(err), err.Error())
	}
	c.session.history = append(c.session.history, protocol.HistoryEntry{Cmd: "act", Payload: payload})
	answer := protocol.ActResponse{
		Events:  result.Events,
		Units:   result.Units,
		Outcome: result.Outcome,
		Board:   b.Summary(),
	}
	if answer.Events == nil {
		answer.Events = []battle.Event{}
	}
	if answer.Units == nil {
		answer.Units = []battle.UnitValues{}
	}
	return protocol.Ok(id, answer)
}

func refusalCode(err error) string {
	switch {
	case errors.Is(err, battle.ErrOutsideContract):
		return protocol.CodeBadRequest
	case errors.Is(err, battle.ErrOffPhase), errors.Is(err, battle.ErrActed), errors.Is(err, battle.ErrBattleOver):
		return protocol.CodeIllegalState
	}
	return protocol.CodeIllegalAction
}
