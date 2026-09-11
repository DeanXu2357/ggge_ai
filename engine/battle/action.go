package battle

type Action struct {
	ActorID        int             `json:"actor_id"` // unit id
	MoveTo         *Cell           `json:"move_to"`
	Attack         *Attack         `json:"attack"`
	ResponseAttack *ResponseAttack `json:"response_attack"`
	MapAttack      *MapAttack      `json:"map_attack"`
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

type MapAttack struct {
	MapWeaponID int       `json:"map_weapon_id"`
	FireCell    Cell      `json:"anchor"`
	Direction   Direction `json:"direction"`
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
