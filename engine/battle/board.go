package battle

type BoardReader interface {
	Actions(unitID string) (ActionsResponse, error)
	ReachableCells(unitID string) ([]Cell, error)
	ResponseAttacks(action *Decision, defenderID string) (ResponseAttacksResponse, error)
	State() BattleState
	Summary() BoardSummary
}

type BoardResolver interface {
	Act(action *Decision, dice Dice) ([]any, error)
	Load(bounds Bounds, terrain Terrain, terrainCells []TerrainCell, units []Unit,
		phase Faction, turn int) error
}

type Board interface {
	BoardReader
	BoardResolver
}
