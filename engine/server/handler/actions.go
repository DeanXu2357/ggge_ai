package handler

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (c *Commands) Actions(id string, payload json.RawMessage) protocol.Response {
	request, b, fail := openCommand[protocol.ActionsRequest](c, id, payload)
	if fail != nil {
		return *fail
	}
	actions, err := b.Actions(request.UnitID)
	if err != nil {
		if errors.Is(err, battle.ErrNoUnit) {
			return protocol.Fail(id, protocol.CodeIllegalAction, err.Error())
		}
		return protocol.Fail(id, protocol.CodeIllegalState, err.Error())
	}
	return protocol.Ok(id, actions)
}

func (c *Commands) ResponseAttacks(id string, payload json.RawMessage) protocol.Response {
	request, b, fail := openCommand[protocol.ResponseAttacksRequest](c, id, payload)
	if fail != nil {
		return *fail
	}
	engagement, err := b.ResponseAttacks(&request.Action, request.DefenderID)
	if err != nil {
		return protocol.Fail(id, refusalCode(err), err.Error())
	}
	return protocol.Ok(id, engagement)
}
