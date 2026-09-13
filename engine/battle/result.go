package battle

type ActResult struct {
	Events  []Event      `json:"events"`
	Units   []UnitValues `json:"units"`
	Outcome Outcome      `json:"outcome"`
}

type Outcome string

const (
	OutcomeOngoing Outcome = "ongoing"
	OutcomeVictory Outcome = "victory"
	OutcomeDefeat  Outcome = "defeat"
)

type Event interface {
	EventKind() EventKind
}

type EventKind string

const (
	EventMove          EventKind = "move"
	EventStrike        EventKind = "strike"
	EventActivationEnd EventKind = "activation_end"
	EventPhase         EventKind = "phase"
)

type MoveEvent struct {
	Kind    EventKind `json:"event"`
	ActorID int       `json:"actor_id"`
	From    Cell      `json:"from"`
	To      Cell      `json:"to"`
}

func (e MoveEvent) EventKind() EventKind { return e.Kind }

type Segment string

const (
	SegmentAttackerSupport Segment = "attacker_support"
	SegmentMain            Segment = "main"
	SegmentDefenderSupport Segment = "defender_support"
	SegmentCounter         Segment = "counter"
)

type StrikeEvent struct {
	Kind      EventKind `json:"event"`
	Segment   Segment   `json:"segment"`
	ShooterID int       `json:"shooter_id"`
	WeaponID  int       `json:"weapon_id"`
	AimedID   int       `json:"aimed_id"`
	StruckID  int       `json:"struck_id"`
	Fired     bool      `json:"fired"`
	Reason    string    `json:"reason,omitempty"`
	Landed    bool      `json:"landed"`
	Critical  bool      `json:"critical"`
	Damage    int       `json:"damage"`
	Effects   []Effect  `json:"effects"`
}

func (e StrikeEvent) EventKind() EventKind { return e.Kind }

type ActivationEndEvent struct {
	Kind    EventKind `json:"event"`
	ActorID int       `json:"actor_id"`
	Effects []Effect  `json:"effects"`
}

func (e ActivationEndEvent) EventKind() EventKind { return e.Kind }

type PhaseEvent struct {
	Kind    EventKind `json:"event"`
	Turn    int       `json:"turn"`
	Phase   Faction   `json:"phase"`
	Effects []Effect  `json:"effects"`
}

func (e PhaseEvent) EventKind() EventKind { return e.Kind }

type Change[T any] struct {
	From T `json:"from"`
	To   T `json:"to"`
}

type Effect struct {
	UnitID               int               `json:"unit_id"`
	HP                   *Change[int]      `json:"hp,omitempty"`
	EN                   *Change[int]      `json:"en,omitempty"`
	SP                   *Change[int]      `json:"sp,omitempty"`
	Pos                  *Change[Cell]     `json:"pos,omitempty"`
	Acted                *Change[bool]     `json:"acted,omitempty"`
	ChanceSteps          *Change[int]      `json:"chance_steps,omitempty"`
	SupportAttackCharges *Change[int]      `json:"support_attack_charges,omitempty"`
	SupportDefendCharges *Change[int]      `json:"support_defend_charges,omitempty"`
	Debuffs              *Change[[]Debuff] `json:"debuffs,omitempty"`
	MapWeaponAmmo        *Change[[]int]    `json:"map_weapon_ammo,omitempty"`
}

type UnitValues struct {
	UnitID               int      `json:"unit_id"`
	Pos                  Cell     `json:"pos"`
	HP                   int      `json:"hp"`
	EN                   int      `json:"en"`
	SP                   int      `json:"sp"`
	Acted                bool     `json:"acted"`
	ChanceSteps          int      `json:"chance_steps"`
	SupportAttackCharges int      `json:"support_attack_charges"`
	SupportDefendCharges int      `json:"support_defend_charges"`
	Skills               []Skill  `json:"skills"`
	MapWeaponAmmo        []int    `json:"map_weapon_ammo"`
	Debuffs              []Debuff `json:"debuffs"`
}
