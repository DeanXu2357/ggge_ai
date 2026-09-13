package system

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

type Forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

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
