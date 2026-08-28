package battle

import "github.com/DeanXu2357/ggge_ai/engine/protocol"

type BoardReader interface {
	Capabilities(unitID string) (protocol.ActionsResponse, error)
	ReachableCells(unitID string) ([]protocol.Cell, error)
	ResponseAttacks(action *protocol.Decision, defenderID string) (protocol.ResponseAttacksResponse, error)
	Clone() Board
	State() protocol.BattleState
	Summary() protocol.BoardSummary
}

type BoardResolver interface {
	Act(action *protocol.Decision, dice Dice) ([]any, error)
}

type Board interface {
	BoardReader
	BoardResolver
}
