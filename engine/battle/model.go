package battle

import (
	"errors"
	"fmt"
	"maps"
	"slices"
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

type WeaponCategory string

const (
	WeaponCategoryRanged WeaponCategory = "ranged"
	WeaponCategoryMelee  WeaponCategory = "melee"
	WeaponCategoryAwaken WeaponCategory = "awaken"
)

var weaponCategories = [...]WeaponCategory{
	WeaponCategoryRanged, WeaponCategoryMelee, WeaponCategoryAwaken,
}

func ParseWeaponCategory(name string) (WeaponCategory, error) {
	for _, known := range weaponCategories {
		if string(known) == name {
			return known, nil
		}
	}
	return "", fmt.Errorf("the weapon category %q is not in the contract", name)
}

type Weapon struct {
	Name            string
	Power           float64
	Range           RadiusRange
	ENCost          int
	Accuracy        float64
	CanCounter      bool
	MapWeapon       bool
	UsableAfterMove bool
	DebuffKind      string
	DebuffMagnitude float64
	Categories      []WeaponCategory
}

type ActionKind string

const (
	ActionAttack     ActionKind = "attack"
	ActionMapAttack  ActionKind = "map_attack"
	ActionReposition ActionKind = "reposition"
	ActionStandby    ActionKind = "standby"
)

// SkillKind names one skill. The set is open until issue #81 says what a
// skill does. It is not an ActionKind.
type SkillKind string

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
	SourcePilot SkillSource = "pilot"
	SourceCrew  SkillSource = "crew"
	SourceMech  SkillSource = "mech"
)

type Debuff struct {
	Kind         string
	Magnitude    float64
	AppliedPhase int
}

// Skill carries no 'self' area. A skill that acts on the caster alone holds a
// range of zero, a blast of zero and the value AffectsAlly: the area is the
// cell of the caster, and the caster is an ally in its own cell.
type Skill struct {
	Kind            SkillKind
	Source          SkillSource
	Amount          *float64
	Uses            int
	EndsActivation  bool
	UsableAfterMove bool
	Range           RadiusRange
	Blast           int
	Affects         SkillAffects
}

type Pilot struct {
	Ranged   float64
	Melee    float64
	Awaken   float64
	Defense  float64
	Reaction float64
	SP       int
}

func (p Pilot) AttackFor(weapon Weapon) float64 {
	categories := weapon.Categories
	if len(categories) == 0 {
		categories = weaponCategories[:]
	}
	highest := p.attackOf(categories[0])
	for _, category := range categories[1:] {
		if value := p.attackOf(category); value > highest {
			highest = value
		}
	}
	return highest
}

func (p Pilot) attackOf(category WeaponCategory) float64 {
	switch category {
	case WeaponCategoryRanged:
		return p.Ranged
	case WeaponCategoryMelee:
		return p.Melee
	case WeaponCategoryAwaken:
		return p.Awaken
	}
	return 0
}

type Mech struct {
	HP        int
	EN        int
	Attack    float64
	Defense   float64
	Mobility  float64
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
	SP                      int
	SPMax                   int
	Pilot                   Pilot
	Mech                    Mech
	Skills                  []Skill
	Acted                   bool
	ChanceSteps             int
	ChanceStepsMax          int
	SupportDefendCharges    int
	SupportDefendChargesMax int
	SupportAttackCharges    int
	SupportAttackChargesMax int
	HasShield               bool
	SupportDefendWhenAttack bool
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
	for index := range u.Mech.Weapons {
		if u.Mech.Weapons[index].Name == name {
			return &u.Mech.Weapons[index]
		}
	}
	return nil
}

// Decision is one activation of one unit. The contract names the payload
// 'action' and the model names it 'Decision'; this package keeps the model
// name.
type Decision struct {
	UnitID         string
	Kind           ActionKind
	MoveTo         *Cell
	TargetID       string
	Weapon         string
	Amount         *float64
	Aim            *Cell
	ResponseAttack *ResponseAttack

	SupportDefender  string
	SupportAttackers []string
}

type ResponseAttack struct {
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

// Before orders two cells: the column first, the row second.
func (c Cell) Before(other Cell) bool {
	if c[0] != other[0] {
		return c[0] < other[0]
	}
	return c[1] < other[1]
}

func (u Unit) Clone() Unit {
	u.Skills = slices.Clone(u.Skills)
	for index := range u.Skills {
		u.Skills[index].Amount = cloneAmount(u.Skills[index].Amount)
	}
	u.Debuffs = slices.Clone(u.Debuffs)
	u.Ammo = maps.Clone(u.Ammo)
	u.Mech.Weapons = slices.Clone(u.Mech.Weapons)
	return u
}

var (
	ErrNoUnit    = errors.New("the board holds no such unit")
	ErrDestroyed = errors.New("the unit is destroyed")
	ErrOffPhase  = errors.New("the unit is not of the current phase")
	ErrActed     = errors.New("the unit acted in this turn")

	ErrIllegalAction = errors.New("the action is not legal")
	ErrIllegalMove   = errors.New("the move is not legal")
)
