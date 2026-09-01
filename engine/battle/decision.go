package battle

// The contract names the payload of one activation 'action'; the struct is
// named 'Decision', and the wire field keeps the contract name. The enum of
// the kinds of one action is 'ActionKind', because the enum holds no kind of
// movement. The wire field stays 'kind'.

type ActionKind string

const (
	ActionAttack     ActionKind = "attack"
	ActionMapAttack  ActionKind = "map_attack"
	ActionReposition ActionKind = "reposition"
	ActionStandby    ActionKind = "standby"
)

type Stance string

const (
	StanceDodge   Stance = "dodge"
	StanceDefend  Stance = "defend"
	StanceCounter Stance = "counter"
	StanceNone    Stance = "none"
)

var (
	actionKinds = map[ActionKind]bool{
		ActionAttack:     true,
		ActionMapAttack:  true,
		ActionReposition: true,
		ActionStandby:    true,
	}
	stances = map[Stance]bool{
		StanceDodge:   true,
		StanceDefend:  true,
		StanceCounter: true,
		StanceNone:    true,
	}
)

func (k *ActionKind) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, k, actionKinds, "kind")
}

func (s *Stance) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, s, stances, "stance")
}

// Every id of this file is a position: a unit id is the position of the unit in
// 'BattleState.Units', a weapon id is the position of the weapon in
// 'Mech.Weapons', and a map weapon id is the position in 'Mech.MapWeapons'.
type ResponseAttack struct {
	Stance             Stance `json:"stance"`
	WeaponID           *int   `json:"weapon_id"`
	SupportDefenderID  *int   `json:"support_defender_id"`
	SupportAttackerIDs []int  `json:"support_attacker_ids"`
}

// Decision carries three dice fields, and each holds three values: the node
// landed, the node missed, and the caller settles the node somewhere else.
type Decision struct {
	UnitID             int             `json:"unit_id"`
	Kind               ActionKind      `json:"kind"`
	MoveTo             *Cell           `json:"move_to"`
	TargetID           *int            `json:"target_id"`
	WeaponID           *int            `json:"weapon_id"`
	MapWeaponID        *int            `json:"map_weapon_id"`
	Amount             *float64        `json:"amount"`
	ResponseAttack     *ResponseAttack `json:"response_attack"`
	SupportDefenderID  *int            `json:"support_defender_id"`
	SupportAttackerIDs []int           `json:"support_attacker_ids"`
	Aim                *Cell           `json:"aim"`
	Hit                *bool           `json:"hit"`
	CounterHit         *bool           `json:"counter_hit"`
	SupportHit         *bool           `json:"support_hit"`
}
