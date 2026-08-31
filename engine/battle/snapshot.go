package battle

import (
	"encoding/json"
	"fmt"
)

// This file is the authority for every struct of the wire form.
// 'src/ggge_ai/engine/state.py' mirrors it, and 'tests/test_engine_codec.py'
// compares the two field lists.

type Cell [2]int

type Faction string

const (
	FactionAlly       Faction = "ally"
	FactionEnemy      Faction = "enemy"
	FactionThirdParty Faction = "third_party"
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

type SkillAffects string

const (
	AffectsAlly  SkillAffects = "ally"
	AffectsEnemy SkillAffects = "enemy"
	AffectsAll   SkillAffects = "all"
)

var (
	factions     = map[Faction]bool{FactionAlly: true, FactionEnemy: true, FactionThirdParty: true}
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

func (s *SkillSource) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, s, skillSources, "source")
}

func (a *SkillAffects) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, a, skillAffects, "affects")
}

// Bounds is the pair of corner cells of the board, the low corner first. The
// wire permits a null; 'board.Validate' refuses a state that carries one.
type Bounds [2]Cell

type Weapon struct {
	Name            string           `json:"name"`
	Power           float64          `json:"power"`
	RangeMin        int              `json:"range_min"`
	RangeMax        int              `json:"range_max"`
	ENCost          int              `json:"en_cost"`
	Accuracy        float64          `json:"accuracy"`
	MapWeapon       bool             `json:"map_weapon"`
	UsableAfterMove bool             `json:"usable_after_move"`
	DebuffKind      *string          `json:"debuff_kind"`
	DebuffMagnitude float64          `json:"debuff_magnitude"`
	Categories      []WeaponCategory `json:"categories"`
}

type Skill struct {
	Kind            SkillKind    `json:"kind"`
	Source          SkillSource  `json:"source"`
	Amount          *float64     `json:"amount"`
	Uses            int          `json:"uses"`
	EndsActivation  bool         `json:"ends_activation"`
	UsableAfterMove bool         `json:"usable_after_move"`
	Affects         SkillAffects `json:"affects"`
}

type Debuff struct {
	Kind         string  `json:"kind"`
	Magnitude    float64 `json:"magnitude"`
	AppliedPhase int     `json:"applied_phase"`
}

// Reaction is the reaction value of the pilot, and not the response attack
// of a defender.
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
	ID                      string         `json:"unit_id"`
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

// TerrainCell binds one cell of the map to one terrain wire name. A cell is a
// JSON pair, so the overrides travel as a list and not as an object.
type TerrainCell struct {
	Cell    Cell    `json:"cell"`
	Terrain Terrain `json:"terrain"`
}

type BattleState struct {
	Units         []Unit        `json:"units"`
	Phase         Faction       `json:"phase"`
	Turn          int           `json:"turn"`
	Bounds        *Bounds       `json:"bounds"`
	PendingEvents []string      `json:"pending_events"`
	FiredEvents   []string      `json:"fired_events"`
	Terrain       Terrain       `json:"terrain,omitempty"`
	TerrainCells  []TerrainCell `json:"terrain_cells,omitempty"`
}
