package battle

type Action struct {
	ActorID        int             `json:"actor_id"` // unit id
	Kind           ActionKind      `json:"kind"`
	MoveTo         *Cell           `json:"move_to"`
	Attack         *Attack         `json:"attack"`
	ResponseAttack *ResponseAttack `json:"response_attack"`
}

type Attack struct {
	WeaponID          int               `json:"weapon_id"`
	TargetID          int               `json:"target_id"`
	Stated            *Stated           `json:"stated"`
	SupportAttackers  []SupportAttacker `json:"support_attackers"`
	SupportDefenderID *int              `json:"support_defender_id"`
}

type ResponseAttack struct {
	Stance            Stance            `json:"stance"`
	WeaponID          *int              `json:"weapon_id"`
	Stated            *Stated           `json:"stated"`
	SupportAttackers  []SupportAttacker `json:"support_attackers"`
	SupportDefenderID *int              `json:"support_defender_id"`
}

type SupportAttacker struct {
	UnitID   int     `json:"unit_id"`
	WeaponID int     `json:"weapon_id"`
	Stated   *Stated `json:"stated"`
}

type Stated struct {
	Crit bool `json:"crit"`
	Hit  bool `json:"hit"`
}
