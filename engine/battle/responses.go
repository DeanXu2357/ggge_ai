package battle

// An answer that lists things in order carries no id field: the position of an
// entry in the list is its id.
type ActionsResponse struct {
	Unit       UnitStatus       `json:"unit"`
	MoveCells  []Cell           `json:"move_cells"`
	Weapons    []WeaponEntry    `json:"weapons"`
	MapWeapons []MapWeaponEntry `json:"map_weapons"`
	Skills     []SkillEntry     `json:"skills"`
}

type UnitStatus struct {
	UnitID    int     `json:"unit_id"`
	Faction   Faction `json:"faction"`
	Pos       Cell    `json:"pos"`
	Size      Cell    `json:"size"`
	HP        int     `json:"hp"`
	MaxHP     int     `json:"max_hp"`
	EN        int     `json:"en"`
	ENMax     int     `json:"en_max"`
	MoveRange int     `json:"move_range"`
	Acted     bool    `json:"acted"`
}

type WeaponEntry struct {
	Name            string  `json:"name"`
	RangeMin        int     `json:"range_min"`
	RangeMax        int     `json:"range_max"`
	ENCost          int     `json:"en_cost"`
	Accuracy        float64 `json:"accuracy"`
	UsableAfterMove bool    `json:"usable_after_move"`
}

type MapWeaponEntry struct {
	Name            string           `json:"name"`
	ApplyShape      ShapeRange       `json:"apply_shape"`
	EffectShape     ShapeRange       `json:"effect_shape"`
	ENCost          int              `json:"en_cost"`
	Ammo            int              `json:"ammo"`
	Accuracy        float64          `json:"accuracy"`
	Affects         MapWeaponAffects `json:"affects"`
	UsableAfterMove bool             `json:"usable_after_move"`
}

type SkillEntry struct {
	Kind            SkillKind    `json:"kind"`
	Amount          *float64     `json:"amount"`
	Uses            int          `json:"uses"`
	EndsActivation  bool         `json:"ends_activation"`
	UsableAfterMove bool         `json:"usable_after_move"`
	ApplyShape      ShapeRange   `json:"apply_shape"`
	EffectShape     ShapeRange   `json:"effect_shape"`
	Affects         SkillAffects `json:"affects"`
}

type ResponseAttacksResponse struct {
	Defender DefenderOptions `json:"defender"`
	Attacker AttackerOptions `json:"attacker"`
}

type Forecast struct {
	HitRate *float64 `json:"hit_rate"`
	Damage  *float64 `json:"damage"`
	Kill    *bool    `json:"kill"`
}

type ResponseAttackOption struct {
	Stance   Stance    `json:"stance"`
	WeaponID *int      `json:"weapon_id"`
	Incoming Forecast  `json:"incoming"`
	Counter  *Forecast `json:"counter,omitempty"`
}

type SupportDefendOption struct {
	UnitID   int      `json:"unit_id"`
	Incoming Forecast `json:"incoming"`
}

type SupportAttackOption struct {
	UnitID   int      `json:"unit_id"`
	WeaponID int      `json:"weapon_id"`
	Strike   Forecast `json:"strike"`
}

type DefenderOptions struct {
	UnitID           int                    `json:"unit_id"`
	ResponseAttacks  []ResponseAttackOption `json:"response_attacks"`
	SupportDefenders []SupportDefendOption  `json:"support_defenders"`
	SupportAttackers []SupportAttackOption  `json:"support_attackers"`
}

type AttackerOptions struct {
	UnitID           int                   `json:"unit_id"`
	SupportDefenders []SupportDefendOption `json:"support_defenders"`
	SupportAttackers []SupportAttackOption `json:"support_attackers"`
}

// An entry of 'events' is a StrikeEvent or a PhaseEvent; the field 'event'
// tells them apart on the wire.
type StrikeEvent struct {
	Event     string `json:"event"`
	Strike    string `json:"strike"`
	ShooterID int    `json:"shooter_id"`
	StruckID  int    `json:"struck_id"`
	WeaponID  int    `json:"weapon_id"`
	Landed    bool   `json:"landed"`
	Damage    int    `json:"damage"`
	Killed    bool   `json:"killed"`
}

type PhaseEvent struct {
	Event string  `json:"event"`
	Turn  int     `json:"turn"`
	Phase Faction `json:"phase"`
}

type BoardSummary struct {
	Turn       int       `json:"turn"`
	Phase      Faction   `json:"phase"`
	PendingIDs []int     `json:"pending_ids"`
	Gone       []Faction `json:"gone"`
}
