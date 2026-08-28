package battle

type CellSet map[Cell]bool

type Forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

type Capabilities struct {
	Unit      *Unit
	MoveCells []Cell
}

type StrikeKind string

const (
	StrikeSupport         StrikeKind = "support"
	StrikeMain            StrikeKind = "strike"
	StrikeDefenderSupport StrikeKind = "defender_support"
	StrikeCounter         StrikeKind = "counter"
)

// The Damage of a skill record is the value that the skill gave back.
type Strike struct {
	Kind      StrikeKind
	ShooterID string
	StruckID  string
	Weapon    string
	Landed    bool
	Damage    int
	Killed    bool
}

type Trace []Strike

type Rotation struct {
	Turn  int
	Phase Faction
}

type Resolution struct {
	Trace     Trace
	Rotations []Rotation
}

type SupportAttacker struct {
	Unit   *Unit
	Weapon *Weapon
}

type ResponseAttackOption struct {
	Stance   Stance
	Weapon   string
	Incoming Forecast
	Counter  *Forecast
}

type SupportDefendOption struct {
	Unit     *Unit
	Incoming Forecast
}

type SupportAttackOption struct {
	Unit   *Unit
	Weapon *Weapon
	Strike Forecast
}

type SideOptions struct {
	Unit             *Unit
	SupportDefenders []SupportDefendOption
	SupportAttackers []SupportAttackOption
}

type Engagement struct {
	Defender        SideOptions
	Attacker        SideOptions
	ResponseAttacks []ResponseAttackOption
}

// BoardReader answers questions about the board and changes nothing.
type BoardReader interface {
	Activatable(unitID string) (*Unit, error)
	BlockingCells(unit *Unit) CellSet
	Bounds() Bounds
	ByFaction(faction Faction) []*Unit
	Capabilities(unitID string) (Capabilities, error)
	Clone() Board
	CounterWeapon(defender *Unit, name string, attacker Footprint) *Weapon
	DefaultTerrain() Terrain
	Gone() []Faction
	OccupiedCells(unit *Unit) CellSet
	Pending(faction Faction) []*Unit
	Phase() Faction
	PhaseIndex() int
	ReachableCells(unitID string) ([]Cell, error)
	ResponseAttacks(action Decision, defenderID string) (Engagement, error)
	Roster() []Unit
	SupportAttackers(supported *Unit, firing, foe Footprint) []SupportAttacker
	SupportDefenders(supported *Unit, at Footprint) []*Unit
	TargetsOf(unit *Unit) []*Unit
	TerrainAt(cell Cell) Terrain
	TerrainCells() map[Cell]Terrain
	TerrainOf(unit *Unit) Terrain
	Turn() int
	Unit(id string) *Unit
}

// BoardResolver carries one decision out and turns the phase over.
type BoardResolver interface {
	Act(decision Decision, dice Dice) (Resolution, error)
	Advance() []Rotation
	Apply(decision Decision, dice Dice) (Trace, error)
}

type Board interface {
	BoardReader
	BoardResolver
}
