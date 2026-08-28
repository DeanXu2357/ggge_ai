package board

type forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

type capabilities struct {
	Unit      *Unit
	MoveCells []cell
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
	Phase faction
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
	Unit     *Unit
	Incoming forecast
}

type supportAttackOption struct {
	Unit   *Unit
	Weapon *Weapon
	Strike forecast
}

type sideOptions struct {
	Unit             *Unit
	SupportDefenders []supportDefendOption
	SupportAttackers []supportAttackOption
}

type engagement struct {
	Defender        sideOptions
	Attacker        sideOptions
	ResponseAttacks []responseAttackOption
}
