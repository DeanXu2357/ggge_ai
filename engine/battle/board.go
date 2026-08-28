package battle

import "github.com/DeanXu2357/ggge_ai/engine/protocol"

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

type BoardReader interface {
	Capabilities(unitID string) (Capabilities, error)
	Clone() Board
	ReachableCells(unitID string) ([]Cell, error)
	ResponseAttacks(action Decision, defenderID string) (Engagement, error)
	State() protocol.BattleState
	Summary() protocol.BoardSummary
}

type BoardResolver interface {
	Act(decision Decision, dice Dice) (Resolution, error)
}

type Board interface {
	BoardReader
	BoardResolver
}
