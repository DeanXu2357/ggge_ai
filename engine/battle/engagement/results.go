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
	ShooterID int
	StruckID  int
	WeaponID  int
	Landed    bool
	Damage    int
	Killed    bool
}

type Trace []Strike

type ResponseAttackOption struct {
	Stance   battle.Stance
	WeaponID *int
	Incoming Forecast
	Counter  *Forecast
}

type SupportDefendOption struct {
	UnitID   int
	Incoming Forecast
}

type SupportAttackOption struct {
	UnitID   int
	WeaponID int
	Strike   Forecast
}

type SideOptions struct {
	UnitID           int
	SupportDefenders []SupportDefendOption
	SupportAttackers []SupportAttackOption
}

type Options struct {
	Defender        SideOptions
	Attacker        SideOptions
	ResponseAttacks []ResponseAttackOption
}
