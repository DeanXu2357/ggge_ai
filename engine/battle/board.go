package battle

type BoardReader interface {
	Actions(unitID int) (ActionsResponse, error)
	ReachableCells(unitID int) ([]Cell, error)
	ResponseAttacks(action *Decision, defenderID int) (ResponseAttacksResponse, error)
	State() BattleState
	Summary() BoardSummary
}

type BoardResolver interface {
	Act(action *Decision, dice Dice) (ActResult, error)
	Load(bounds Bounds, terrain Terrain, terrainCells []TerrainCell, units []Unit,
		phase Faction, turn int) error
}

type Board interface {
	BoardReader
	BoardResolver
}
