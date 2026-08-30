package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

type capabilities struct {
	Unit      *state.Unit
	MoveCells []state.Cell
}

type strikeKind string

const (
	strikeSupport         strikeKind = "support"
	strikeMain            strikeKind = "strike"
	strikeDefenderSupport strikeKind = "defender_support"
	strikeCounter         strikeKind = "counter"
)

// The Damage of a skill record is the value that the skill gave back.
type strike struct {
	Kind      strikeKind
	ShooterID string
	StruckID  string
	Weapon    string
	Landed    bool
	Damage    int
	Killed    bool
}

type trace []strike

type rotation struct {
	Turn  int
	Phase state.Faction
}

type resolution struct {
	Trace     trace
	Rotations []rotation
}

type responseAttackOption struct {
	Stance   stance
	Weapon   string
	Incoming forecast
	Counter  *forecast
}

type supportDefendOption struct {
	Unit     *state.Unit
	Incoming forecast
}

type supportAttackOption struct {
	Unit   *state.Unit
	Weapon *def.Weapon
	Strike forecast
}

type sideOptions struct {
	Unit             *state.Unit
	SupportDefenders []supportDefendOption
	SupportAttackers []supportAttackOption
}

type engagement struct {
	Defender        sideOptions
	Attacker        sideOptions
	ResponseAttacks []responseAttackOption
}
