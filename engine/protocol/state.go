package protocol

import (
	"encoding/json"
	"fmt"
)

// The authority for every struct in this file is 'src/ggge_ai/sandbox/model.py'.
// The contract names the payload of one activation 'action'; the model names
// the same thing 'Decision', and this package keeps the model name for the type
// and the contract name for the wire field. The model names the enum of the
// kinds of one action 'MoveKind'; this package names it ActionKind, because the
// enum holds no kind of movement. The wire field stays 'kind'.

type Faction string

const (
	FactionAlly       Faction = "ally"
	FactionEnemy      Faction = "enemy"
	FactionThirdParty Faction = "third_party"
)

type ActionKind string

const (
	ActionAttack      ActionKind = "attack"
	ActionMapAttack   ActionKind = "map_attack"
	ActionReposition  ActionKind = "reposition"
	ActionStandby     ActionKind = "standby"
	ActionSkillRefill ActionKind = "skill_en_refill"
	ActionSkillHeal   ActionKind = "skill_heal"
)

type SkillSource string

const (
	SourceCharacter SkillSource = "character"
	SourceCrew      SkillSource = "crew"
	SourceUnit      SkillSource = "unit"
)

// SkillAffects holds no 'self' value. A skill that acts on the caster alone
// carries a range of zero, a blast of zero and the value ally: the area is the
// cell of the caster, and the caster is an ally in its own cell.
type SkillAffects string

const (
	AffectsAlly  SkillAffects = "ally"
	AffectsEnemy SkillAffects = "enemy"
	AffectsAll   SkillAffects = "all"
)

// The reaction menu of the game holds no decline button, so the contract lists
// no 'none' stance (docs/spec/battle-engine-protocol.md, issue #56). The model
// keeps 'none' for a strike that settles no reaction; that value never reaches
// the wire.
type Stance string

const (
	StanceDodge   Stance = "dodge"
	StanceDefend  Stance = "defend"
	StanceShield  Stance = "shield"
	StanceCounter Stance = "counter"
)

var (
	factions    = map[Faction]bool{FactionAlly: true, FactionEnemy: true, FactionThirdParty: true}
	actionKinds = map[ActionKind]bool{
		ActionAttack:      true,
		ActionMapAttack:   true,
		ActionReposition:  true,
		ActionStandby:     true,
		ActionSkillRefill: true,
		ActionSkillHeal:   true,
	}
	stances = map[Stance]bool{
		StanceDodge:   true,
		StanceDefend:  true,
		StanceShield:  true,
		StanceCounter: true,
	}
	skillSources = map[SkillSource]bool{
		SourceCharacter: true,
		SourceCrew:      true,
		SourceUnit:      true,
	}
	skillAffects = map[SkillAffects]bool{
		AffectsAlly:  true,
		AffectsEnemy: true,
		AffectsAll:   true,
	}
)

func decodeEnum[T ~string](data []byte, out *T, known map[T]bool, name string) error {
	var raw string
	if err := json.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	if !known[T(raw)] {
		return fmt.Errorf("%s %q is not in the contract", name, raw)
	}
	*out = T(raw)
	return nil
}

func (f *Faction) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, f, factions, "faction")
}

func (k *ActionKind) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, k, actionKinds, "kind")
}

func (s *Stance) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, s, stances, "stance")
}

func (s *SkillSource) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, s, skillSources, "source")
}

func (a *SkillAffects) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, a, skillAffects, "affects")
}

// Bounds is the pair of corner cells of the board. A state with no bounds runs
// on an open plane; it is not an empty board.
type Bounds [2]Cell

type Rules struct {
	DefendMultiplier        float64 `json:"defend_multiplier"`
	ShieldMultiplier        float64 `json:"shield_multiplier"`
	SupportDefendMultiplier float64 `json:"support_defend_multiplier"`
	DodgeHitPenalty         float64 `json:"dodge_hit_penalty"`
	Terrain                 float64 `json:"terrain"`
	MaxSupportAttackers     int     `json:"max_support_attackers"`
	ENRegenFraction         float64 `json:"en_regen_fraction"`
}

type Weapon struct {
	Name            string  `json:"name"`
	Power           float64 `json:"power"`
	RangeMin        int     `json:"range_min"`
	RangeMax        int     `json:"range_max"`
	ENCost          int     `json:"en_cost"`
	Accuracy        float64 `json:"accuracy"`
	CanCounter      bool    `json:"can_counter"`
	MapWeapon       bool    `json:"map_weapon"`
	UsableAfterMove bool    `json:"usable_after_move"`
	Blast           int     `json:"blast"`
	DebuffKind      *string `json:"debuff_kind"`
	DebuffMagnitude float64 `json:"debuff_magnitude"`
}

type Skill struct {
	Kind            ActionKind   `json:"kind"`
	Source          SkillSource  `json:"source"`
	Amount          *float64     `json:"amount"`
	Uses            int          `json:"uses"`
	EndsActivation  bool         `json:"ends_activation"`
	UsableAfterMove bool         `json:"usable_after_move"`
	RangeMin        int          `json:"range_min"`
	RangeMax        int          `json:"range_max"`
	Blast           int          `json:"blast"`
	Affects         SkillAffects `json:"affects"`
}

type Debuff struct {
	Kind         string  `json:"kind"`
	Magnitude    float64 `json:"magnitude"`
	AppliedPhase int     `json:"applied_phase"`
}

// Two names mislead: Reaction is the reaction value of the pilot, not the
// Reaction type of a defense, and ChanceSteps is the re-act grant after a kill
// (docs/reference/combat-formulas.md:134), which counts no dice.
type Unit struct {
	UnitID                  string         `json:"unit_id"`
	Faction                 Faction        `json:"faction"`
	Pos                     Cell           `json:"pos"`
	Size                    Cell           `json:"size"`
	HP                      int            `json:"hp"`
	MaxHP                   int            `json:"max_hp"`
	EN                      int            `json:"en"`
	ENMax                   int            `json:"en_max"`
	UnitAttack              float64        `json:"unit_attack"`
	UnitDefense             float64        `json:"unit_defense"`
	PilotAttack             float64        `json:"pilot_attack"`
	PilotDefense            float64        `json:"pilot_defense"`
	Reaction                float64        `json:"reaction"`
	Mobility                float64        `json:"mobility"`
	MoveRange               int            `json:"move_range"`
	Weapons                 []Weapon       `json:"weapons"`
	Skills                  []Skill        `json:"skills"`
	Acted                   bool           `json:"acted"`
	ChanceSteps             int            `json:"chance_steps"`
	ChanceStepsMax          int            `json:"chance_steps_max"`
	SupportDefendCharges    int            `json:"support_defend_charges"`
	SupportDefendChargesMax int            `json:"support_defend_charges_max"`
	SupportAttackCharges    int            `json:"support_attack_charges"`
	SupportAttackChargesMax int            `json:"support_attack_charges_max"`
	HasShield               bool           `json:"has_shield"`
	AttackShield            bool           `json:"attack_shield"`
	InterceptionReduction   float64        `json:"interception_reduction"`
	Ammo                    map[string]int `json:"ammo"`
	Debuffs                 []Debuff       `json:"debuffs"`
}

type Reaction struct {
	Stance        Stance  `json:"stance"`
	Weapon        *string `json:"weapon"`
	SupportDefend bool    `json:"support_defend"`
	SupportAttack bool    `json:"support_attack"`
}

// Decision carries three dice fields, and each holds three values: the node
// landed, the node missed, and the caller settles the node somewhere else.
type Decision struct {
	UnitID     string     `json:"unit_id"`
	Kind       ActionKind `json:"kind"`
	MoveTo     *Cell      `json:"move_to"`
	TargetID   *string    `json:"target_id"`
	Weapon     *string    `json:"weapon"`
	Amount     *float64   `json:"amount"`
	Reaction   *Reaction  `json:"reaction"`
	Support    bool       `json:"support"`
	Aim        *Cell      `json:"aim"`
	Hit        *bool      `json:"hit"`
	CounterHit *bool      `json:"counter_hit"`
	SupportHit *bool      `json:"support_hit"`
}

// StageEvent keeps its trigger and its effect raw: the model holds them as free
// dicts, and the issue that runs the event table reads them.
type StageEvent struct {
	EventID string          `json:"event_id"`
	Trigger json.RawMessage `json:"trigger"`
	Effect  json.RawMessage `json:"effect"`
}

type EventTable = map[string]StageEvent

type BattleState struct {
	Units         []Unit   `json:"units"`
	Phase         Faction  `json:"phase"`
	Turn          int      `json:"turn"`
	Bounds        *Bounds  `json:"bounds"`
	PendingEvents []string `json:"pending_events"`
	FiredEvents   []string `json:"fired_events"`
}

// A chance event is one random node of a resolution. The three consumption
// modes read the same type: enumerate walks every outcome, sampled draws one
// with these probabilities, and forced takes the outcome whose label the
// request names in Dice.Outcomes. The label set of a node belongs to the issue
// that implements the node.
type ChanceEvent struct {
	ID       string          `json:"id"`
	Kind     string          `json:"kind"`
	Outcomes []ChanceOutcome `json:"outcomes"`
}

type ChanceOutcome struct {
	Label       string  `json:"label"`
	Probability float64 `json:"probability"`
}
