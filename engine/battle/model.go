package battle

import (
	"errors"
	"fmt"
)

type Cell [2]int

type Size [2]int

type Footprint struct {
	Anchor Cell
	Size   Size
}

func (f Footprint) Within(bounds Bounds) bool {
	high := Cell{f.Anchor[0] + f.Size[0] - 1, f.Anchor[1] + f.Size[1] - 1}
	return bounds.Low[0] <= f.Anchor[0] && high[0] <= bounds.High[0] &&
		bounds.Low[1] <= f.Anchor[1] && high[1] <= bounds.High[1]
}

func (f Footprint) Cells() []Cell {
	out := make([]Cell, 0, f.Size[0]*f.Size[1])
	for dx := 0; dx < f.Size[0]; dx++ {
		for dy := 0; dy < f.Size[1]; dy++ {
			out = append(out, Cell{f.Anchor[0] + dx, f.Anchor[1] + dy})
		}
	}
	return out
}

type Bounds struct {
	Low  Cell
	High Cell
}

type RadiusRange struct {
	Min int
	Max int
}

func (r RadiusRange) Holds(distance int) bool {
	return r.Min <= distance && distance <= r.Max
}

type Faction string

const (
	FactionAlly       Faction = "ally"
	FactionEnemy      Faction = "enemy"
	FactionThirdParty Faction = "third_party"
)

func (f Faction) Opposing() Faction {
	if f == FactionAlly {
		return FactionEnemy
	}
	return FactionAlly
}

// A weapon that declares no restriction deals full damage against every
// terrain and fires from every terrain: an absent entry of TerrainDamage is
// 1.0, and an absent entry of UnusableIn permits the shot.
// A weapon with an empty DebuffKind applies no debuff.
type Weapon struct {
	Name            string
	Power           float64
	Range           RadiusRange
	ENCost          int
	Accuracy        float64
	CanCounter      bool
	MapWeapon       bool
	UsableAfterMove bool
	Blast           int
	DebuffKind      string
	DebuffMagnitude float64
	TerrainDamage   map[Terrain]float64
	UnusableIn      TerrainSet
}

func (w Weapon) DamageScaleAgainst(target Terrain) float64 {
	if scale, declared := w.TerrainDamage[target]; declared {
		return scale
	}
	return 1
}

func (w Weapon) UsableIn(attacker Terrain) bool {
	return !w.UnusableIn[attacker]
}

type ActionKind string

const (
	ActionAttack      ActionKind = "attack"
	ActionMapAttack   ActionKind = "map_attack"
	ActionReposition  ActionKind = "reposition"
	ActionStandby     ActionKind = "standby"
	ActionSkillRefill ActionKind = "skill_en_refill"
	ActionSkillHeal   ActionKind = "skill_heal"
)

type Stance string

const (
	StanceDodge   Stance = "dodge"
	StanceDefend  Stance = "defend"
	StanceCounter Stance = "counter"
	StanceNone    Stance = "none"
)

type SkillAffects string

const (
	AffectsAlly  SkillAffects = "ally"
	AffectsEnemy SkillAffects = "enemy"
	AffectsAll   SkillAffects = "all"
)

type SkillSource string

const (
	SourceCharacter SkillSource = "character"
	SourceCrew      SkillSource = "crew"
	SourceUnit      SkillSource = "unit"
)

// Rules holds the multipliers and the limits of the mechanism.
// docs/reference/combat-formulas.md gives the values of DefaultRules, and a
// stage overrides them in its rules payload.
type Rules struct {
	DefendMultiplier        float64
	ShieldMultiplier        float64
	SupportDefendMultiplier float64
	DodgeHitPenalty         float64
	Terrain                 float64
	MaxSupportAttackers     int
	ENRegenFraction         float64
}

func DefaultRules() Rules {
	return Rules{
		DefendMultiplier:        DefendMultiplier,
		ShieldMultiplier:        ShieldMultiplier,
		SupportDefendMultiplier: DefendMultiplier,
		DodgeHitPenalty:         20,
		Terrain:                 1,
		MaxSupportAttackers:     3,
		ENRegenFraction:         0.10,
	}
}

type Debuff struct {
	Kind         string
	Magnitude    float64
	AppliedPhase int
}

// Skill carries no 'self' area. A skill that acts on the caster alone holds a
// range of zero, a blast of zero and the value AffectsAlly: the area is the
// cell of the caster, and the caster is an ally in its own cell.
type Skill struct {
	Kind            ActionKind
	Source          SkillSource
	Amount          *float64
	Uses            int
	EndsActivation  bool
	UsableAfterMove bool
	Range           RadiusRange
	Blast           int
	Affects         SkillAffects
}

// Pilot and Mech hold base data: the values the character and the machine
// bring to the computation. Unit holds the final panel: the values the game
// shows for the deployed piece, after every ability of the pilot and of the
// mech. No rule derives the one from the other yet, so each level takes its
// own wire field.
type Pilot struct {
	Attack   float64
	Defense  float64
	Reaction float64
}

type Mech struct {
	Attack    float64
	Defense   float64
	Mobility  float64
	HP        int
	EN        int
	MoveRange int
	Weapons   []Weapon
}

type Unit struct {
	ID                      string
	Faction                 Faction
	Footprint               Footprint
	HP                      int
	MaxHP                   int
	EN                      int
	ENMax                   int
	Pilot                   Pilot
	Mech                    Mech
	MoveRange               int
	Weapons                 []Weapon
	Skills                  []Skill
	Acted                   bool
	ChanceSteps             int
	ChanceStepsMax          int
	SupportDefendCharges    int
	SupportDefendChargesMax int
	SupportAttackCharges    int
	SupportAttackChargesMax int
	HasShield               bool
	AttackShield            bool
	InterceptionReduction   float64
	Ammo                    map[string]int
	Debuffs                 []Debuff
}

func (u *Unit) Alive() bool {
	return u != nil && u.HP > 0
}

func (u *Unit) HasENFor(weapon Weapon) bool {
	return u.EN >= weapon.ENCost
}

func (u *Unit) Weapon(name string) *Weapon {
	for index := range u.Weapons {
		if u.Weapons[index].Name == name {
			return &u.Weapons[index]
		}
	}
	return nil
}

// Skill gives the first skill of that kind with a use left that gives the
// amount, or nil. A unit carries no name for a skill, so the kind and the
// amount of the action name it; a unit can hold two skills of one kind.
func (u *Unit) Skill(kind ActionKind, amount *float64) *Skill {
	for index := range u.Skills {
		skill := &u.Skills[index]
		if skill.Kind == kind && skill.Uses > 0 && sameAmount(skill.Amount, amount) {
			return skill
		}
	}
	return nil
}

func sameAmount(one, other *float64) bool {
	if one == nil || other == nil {
		return one == nil && other == nil
	}
	return *one == *other
}

// Decision is one activation of one unit. The contract names the payload
// 'action' and the model names it 'Decision'; this package keeps the model
// name.
type Decision struct {
	UnitID   string
	Kind     ActionKind
	MoveTo   *Cell
	TargetID string
	Weapon   string
	Amount   *float64
	Aim      *Cell
	Reaction *Reaction

	// SupportAttackers holds the units of the side of the actor that join the
	// strike. The client names them; the engine reports which units are
	// eligible and judges the pick (issue #63).
	SupportAttackers []string
}

// Reaction is the answer the defender picks against one strike. SupportDefender
// is the interceptor that takes the strike in place of the defender, and it is
// empty when the defender takes the strike itself.
type Reaction struct {
	Stance           Stance
	Weapon           string
	SupportDefender  string
	SupportAttackers []string
}

func cloneAmount(amount *float64) *float64 {
	if amount == nil {
		return nil
	}
	out := *amount
	return &out
}

func NewBoard(bounds Bounds, units []Unit, rules Rules) (*Board, error) {
	if bounds.High[0] < bounds.Low[0] || bounds.High[1] < bounds.Low[1] {
		return nil, fmt.Errorf("the bounds %v run backward", bounds)
	}
	seen := make(map[string]bool, len(units))
	for index := range units {
		id := units[index].ID
		if seen[id] {
			return nil, fmt.Errorf("the board holds two units with the id %q", id)
		}
		seen[id] = true
	}
	return &Board{Bounds: bounds, Units: units, Rules: rules}, nil
}

type Board struct {
	Bounds         Bounds
	Units          []Unit
	Phase          Faction
	Turn           int
	Rules          Rules
	DefaultTerrain Terrain
	TerrainCells   map[Cell]Terrain
}

func (b *Board) TerrainAt(cell Cell) Terrain {
	if kind, declared := b.TerrainCells[cell]; declared {
		return kind
	}
	return b.DefaultTerrain
}

func (b *Board) TerrainOf(unit *Unit) Terrain {
	if unit == nil {
		return b.DefaultTerrain
	}
	return b.TerrainAt(unit.Footprint.Anchor)
}

// PhaseOrder is the order in which the three sides act. A debuff of one turn
// lives for the length of this order (docs/reference/combat-formulas.md).
var PhaseOrder = [...]Faction{FactionAlly, FactionThirdParty, FactionEnemy}

// PhaseIndex counts the phases from the start of the battle. A debuff records
// the index of the phase that applied it.
func (b *Board) PhaseIndex() int {
	for index, faction := range PhaseOrder {
		if faction == b.Phase {
			return b.Turn*len(PhaseOrder) + index
		}
	}
	return b.Turn * len(PhaseOrder)
}

func (b *Board) Unit(id string) *Unit {
	for index := range b.Units {
		if b.Units[index].ID == id {
			return &b.Units[index]
		}
	}
	return nil
}

var (
	ErrNoUnit    = errors.New("the board holds no such unit")
	ErrDestroyed = errors.New("the unit is destroyed")
	ErrOffPhase  = errors.New("the unit is not of the current phase")
	ErrActed     = errors.New("the unit acted in this turn")
)

// Activatable gives the unit that can act now, or the sentinel error that names
// the refusal. The command 'act' reads this gate; the reporting commands do
// not, because a report of a unit that acted is still the answer to the
// question.
func (b *Board) Activatable(unitID string) (*Unit, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return nil, err
	}
	if unit.Faction != b.Phase {
		return nil, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			ErrOffPhase, unitID, unit.Faction, b.Phase)
	}
	if unit.Acted {
		return nil, fmt.Errorf("%w: %q", ErrActed, unitID)
	}
	return unit, nil
}

func (b *Board) livingUnit(id string) (*Unit, error) {
	unit := b.Unit(id)
	if unit == nil {
		return nil, fmt.Errorf("%w: %q", ErrNoUnit, id)
	}
	if !unit.Alive() {
		return nil, fmt.Errorf("%w: %q", ErrDestroyed, id)
	}
	return unit, nil
}

func (b *Board) Roster() []Unit {
	panic("to be implemented")
}

func (b *Board) ReachableCells(unitID string) ([]Cell, error) {
	unit := b.Unit(unitID)
	if unit == nil {
		return nil, fmt.Errorf("the board holds no unit %q", unitID)
	}
	return SortedCells(b.reachableAnchors(unit)), nil
}

func (b *Board) reachableAnchors(unit *Unit) CellSet {
	return ReachableAnchors(unit.Footprint, unit.MoveRange,
		b.BlockingCells(unit), b.OccupiedCells(unit), b.Bounds)
}

func (b *Board) ByFaction(faction Faction) []*Unit {
	var out []*Unit
	for index := range b.Units {
		other := &b.Units[index]
		if other.Faction == faction && other.Alive() {
			out = append(out, other)
		}
	}
	return out
}

func (b *Board) TargetsOf(unit *Unit) []*Unit {
	return b.ByFaction(unit.Faction.Opposing())
}

func (b *Board) BlockingCells(unit *Unit) CellSet {
	out := CellSet{}
	for index := range b.Units {
		other := &b.Units[index]
		if other.ID == unit.ID || !other.Alive() || other.Faction == unit.Faction {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}

func (b *Board) OccupiedCells(unit *Unit) CellSet {
	out := CellSet{}
	for index := range b.Units {
		other := &b.Units[index]
		if other.ID == unit.ID || !other.Alive() {
			continue
		}
		addFootprint(out, other.Footprint)
	}
	return out
}
