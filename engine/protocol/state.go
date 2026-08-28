package protocol

import (
	"encoding/json"
	"fmt"
)

// This file is the authority for every struct of the wire form.
// 'src/ggge_ai/engine/state.py' mirrors it, and 'tests/test_engine_codec.py'
// compares the two field lists. The contract names the payload of one
// activation 'action'; the struct is named 'Decision', and the wire field
// keeps the contract name. The enum of the kinds of one action is
// 'ActionKind', because the enum holds no kind of movement. The wire field
// stays 'kind'.

type Faction string

const (
	FactionAlly       Faction = "ally"
	FactionEnemy      Faction = "enemy"
	FactionThirdParty Faction = "third_party"
)

type ActionKind string

const (
	ActionAttack     ActionKind = "attack"
	ActionMapAttack  ActionKind = "map_attack"
	ActionReposition ActionKind = "reposition"
	ActionStandby    ActionKind = "standby"
)

// SkillKind names one skill. The set is open: no contract of this repository
// says what a skill does, so the decoder validates nothing and the engine
// resolves nothing (issue #81). It is not an ActionKind: what a skill does is
// not a kind of action.
type SkillKind string

type SkillSource string

const (
	SourcePilot SkillSource = "pilot"
	SourceCrew  SkillSource = "crew"
	SourceMech  SkillSource = "mech"
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

type Stance string

const (
	StanceDodge   Stance = "dodge"
	StanceDefend  Stance = "defend"
	StanceCounter Stance = "counter"
	StanceNone    Stance = "none"
)

var (
	factions    = map[Faction]bool{FactionAlly: true, FactionEnemy: true, FactionThirdParty: true}
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
	skillSources = map[SkillSource]bool{
		SourcePilot: true,
		SourceCrew:  true,
		SourceMech:  true,
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

type Weapon struct {
	Name            string   `json:"name"`
	Power           float64  `json:"power"`
	RangeMin        int      `json:"range_min"`
	RangeMax        int      `json:"range_max"`
	ENCost          int      `json:"en_cost"`
	Accuracy        float64  `json:"accuracy"`
	CanCounter      bool     `json:"can_counter"`
	MapWeapon       bool     `json:"map_weapon"`
	UsableAfterMove bool     `json:"usable_after_move"`
	DebuffKind      *string  `json:"debuff_kind"`
	DebuffMagnitude float64  `json:"debuff_magnitude"`
	Categories      []string `json:"categories"`
}

type Skill struct {
	Kind            SkillKind    `json:"kind"`
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

// Reaction is the reaction value of the pilot, and not the Reaction type of a
// defense.
type Pilot struct {
	Ranged   float64 `json:"ranged"`
	Melee    float64 `json:"melee"`
	Awaken   float64 `json:"awaken"`
	Defense  float64 `json:"defense"`
	Reaction float64 `json:"reaction"`
	SP       int     `json:"sp"`
}

type Mech struct {
	HP        int      `json:"hp"`
	EN        int      `json:"en"`
	Attack    float64  `json:"attack"`
	Defense   float64  `json:"defense"`
	Mobility  float64  `json:"mobility"`
	MoveRange int      `json:"move_range"`
	Weapons   []Weapon `json:"weapons"`
}

// Unit is the current state of the pairing on the board. It holds the state
// and the maxima of the state; the pilot and the mech hold the values that a
// formula reads. ChanceSteps is the re-act grant after a kill
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
	SP                      int            `json:"sp"`
	SPMax                   int            `json:"sp_max"`
	Pilot                   Pilot          `json:"pilot"`
	Mech                    Mech           `json:"mech"`
	Skills                  []Skill        `json:"skills"`
	Acted                   bool           `json:"acted"`
	ChanceSteps             int            `json:"chance_steps"`
	ChanceStepsMax          int            `json:"chance_steps_max"`
	SupportDefendCharges    int            `json:"support_defend_charges"`
	SupportDefendChargesMax int            `json:"support_defend_charges_max"`
	SupportAttackCharges    int            `json:"support_attack_charges"`
	SupportAttackChargesMax int            `json:"support_attack_charges_max"`
	HasShield               bool           `json:"has_shield"`
	SupportDefendWhenAttack bool           `json:"support_defend_when_attack"`
	Ammo                    map[string]int `json:"ammo"`
	Debuffs                 []Debuff       `json:"debuffs"`
}

type Reaction struct {
	Stance           Stance   `json:"stance"`
	Weapon           *string  `json:"weapon"`
	SupportDefender  *string  `json:"support_defender"`
	SupportAttackers []string `json:"support_attackers"`
}

// Decision carries three dice fields, and each holds three values: the node
// landed, the node missed, and the caller settles the node somewhere else.
type Decision struct {
	UnitID           string     `json:"unit_id"`
	Kind             ActionKind `json:"kind"`
	MoveTo           *Cell      `json:"move_to"`
	TargetID         *string    `json:"target_id"`
	Weapon           *string    `json:"weapon"`
	Amount           *float64   `json:"amount"`
	Reaction         *Reaction  `json:"reaction"`
	SupportDefender  *string    `json:"support_defender"`
	SupportAttackers []string   `json:"support_attackers"`
	Aim              *Cell      `json:"aim"`
	Hit              *bool      `json:"hit"`
	CounterHit       *bool      `json:"counter_hit"`
	SupportHit       *bool      `json:"support_hit"`
}

// StageEvent keeps its trigger and its effect raw: the model holds them as free
// dicts, and the issue that runs the event table reads them.
type StageEvent struct {
	EventID string          `json:"event_id"`
	Trigger json.RawMessage `json:"trigger"`
	Effect  json.RawMessage `json:"effect"`
}

type EventTable = map[string]StageEvent

// TerrainCell binds one cell of the map to one terrain wire name. A cell is a
// JSON pair, so the overrides travel as a list and not as an object.
type TerrainCell struct {
	Cell    Cell   `json:"cell"`
	Terrain string `json:"terrain"`
}

type BattleState struct {
	Units         []Unit        `json:"units"`
	Phase         Faction       `json:"phase"`
	Turn          int           `json:"turn"`
	Bounds        *Bounds       `json:"bounds"`
	PendingEvents []string      `json:"pending_events"`
	FiredEvents   []string      `json:"fired_events"`
	Terrain       string        `json:"terrain,omitempty"`
	TerrainCells  []TerrainCell `json:"terrain_cells,omitempty"`
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
