package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
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
	Stance   battle.Stance
	Weapon   string
	Incoming Forecast
	Counter  *Forecast
}

type SupportDefendOption struct {
	Unit     *state.Unit
	Incoming Forecast
}

type SupportAttackOption struct {
	Unit   *state.Unit
	Weapon *def.Weapon
	Strike Forecast
}

type SideOptions struct {
	Unit             *state.Unit
	SupportDefenders []SupportDefendOption
	SupportAttackers []SupportAttackOption
}

type Options struct {
	Defender        SideOptions
	Attacker        SideOptions
	ResponseAttacks []ResponseAttackOption
}
