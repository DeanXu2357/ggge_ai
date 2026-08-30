package battle

type BoardReader interface {
	Actions(unitID string) (ActionsResponse, error)
	ReachableCells(unitID string) ([]Cell, error)
	ResponseAttacks(action *Decision, defenderID string) (ResponseAttacksResponse, error)
	Clone() Board
	State() BattleState
	Summary() BoardSummary
}

type BoardResolver interface {
	Act(action *Decision, dice Dice) ([]any, error)
}

type Board interface {
	BoardReader
	BoardResolver
}
