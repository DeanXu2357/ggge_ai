package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

type Forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
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

type ResponseAttackOption struct {
	Stance   Stance
	Weapon   string
	Incoming Forecast
	Counter  *Forecast
}

type SupportDefendOption struct {
	Unit     *battle.Unit
	Incoming Forecast
}

type SupportAttackOption struct {
	Unit   *battle.Unit
	Weapon *battle.Weapon
	Strike Forecast
}

type SideOptions struct {
	Unit             *battle.Unit
	SupportDefenders []SupportDefendOption
	SupportAttackers []SupportAttackOption
}

type Options struct {
	Defender        SideOptions
	Attacker        SideOptions
	ResponseAttacks []ResponseAttackOption
}
