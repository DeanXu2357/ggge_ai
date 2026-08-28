package board

import (
	"fmt"
	"maps"
	"slices"
)

type cell [2]int

type size [2]int

type footprint struct {
	Anchor cell
	Size   size
}

func (f footprint) within(bounds bounds) bool {
	high := cell{f.Anchor[0] + f.Size[0] - 1, f.Anchor[1] + f.Size[1] - 1}
	return bounds.Low[0] <= f.Anchor[0] && high[0] <= bounds.High[0] &&
		bounds.Low[1] <= f.Anchor[1] && high[1] <= bounds.High[1]
}

func (f footprint) cells() []cell {
	out := make([]cell, 0, f.Size[0]*f.Size[1])
	for dx := 0; dx < f.Size[0]; dx++ {
		for dy := 0; dy < f.Size[1]; dy++ {
			out = append(out, cell{f.Anchor[0] + dx, f.Anchor[1] + dy})
		}
	}
	return out
}

type bounds struct {
	Low  cell
	High cell
}

type radiusRange struct {
	Min int
	Max int
}

func (r radiusRange) holds(distance int) bool {
	return r.Min <= distance && distance <= r.Max
}

type faction string

const (
	factionAlly       faction = "ally"
	factionEnemy      faction = "enemy"
	factionThirdParty faction = "third_party"
)

func (f faction) opposing() faction {
	if f == factionAlly {
		return factionEnemy
	}
	return factionAlly
}

type weaponCategory string

const (
	weaponCategoryRanged weaponCategory = "ranged"
	weaponCategoryMelee  weaponCategory = "melee"
	weaponCategoryAwaken weaponCategory = "awaken"
)

var weaponCategories = [...]weaponCategory{
	weaponCategoryRanged, weaponCategoryMelee, weaponCategoryAwaken,
}

func parseWeaponCategory(name string) (weaponCategory, error) {
	for _, known := range weaponCategories {
		if string(known) == name {
			return known, nil
		}
	}
	return "", fmt.Errorf("the weapon category %q is not in the contract", name)
}

type weapon struct {
	Name            string
	Power           float64
	Range           radiusRange
	ENCost          int
	Accuracy        float64
	CanCounter      bool
	MapWeapon       bool
	UsableAfterMove bool
	DebuffKind      string
	DebuffMagnitude float64
	Categories      []weaponCategory
}

type actionKind string

const (
	actionAttack     actionKind = "attack"
	actionMapAttack  actionKind = "map_attack"
	actionReposition actionKind = "reposition"
	actionStandby    actionKind = "standby"
)

// skillKind names one skill. The set is open until issue #81 says what a
// skill does. It is not an actionKind.
type skillKind string

type stance string

const (
	stanceDodge   stance = "dodge"
	stanceDefend  stance = "defend"
	stanceCounter stance = "counter"
	stanceNone    stance = "none"
)

type skillAffects string

const (
	affectsAlly  skillAffects = "ally"
	affectsEnemy skillAffects = "enemy"
	affectsAll   skillAffects = "all"
)

type skillSource string

const (
	sourcePilot skillSource = "pilot"
	sourceCrew  skillSource = "crew"
	sourceMech  skillSource = "mech"
)

type debuff struct {
	Kind         string
	Magnitude    float64
	AppliedPhase int
}

// skill carries no 'self' area. A skill that acts on the caster alone holds a
// range of zero, a blast of zero and the value affectsAlly: the area is the
// cell of the caster, and the caster is an ally in its own cell.
type skill struct {
	Kind            skillKind
	Source          skillSource
	Amount          *float64
	Uses            int
	EndsActivation  bool
	UsableAfterMove bool
	Range           radiusRange
	Blast           int
	Affects         skillAffects
}

type pilot struct {
	Ranged   float64
	Melee    float64
	Awaken   float64
	Defense  float64
	Reaction float64
	SP       int
}

func (p pilot) attackFor(weapon weapon) float64 {
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

func (p pilot) attackOf(category weaponCategory) float64 {
	switch category {
	case weaponCategoryRanged:
		return p.Ranged
	case weaponCategoryMelee:
		return p.Melee
	case weaponCategoryAwaken:
		return p.Awaken
	}
	return 0
}

type mech struct {
	HP        int
	EN        int
	Attack    float64
	Defense   float64
	Mobility  float64
	MoveRange int
	Weapons   []weapon
}

type unit struct {
	ID                      string
	Faction                 faction
	Footprint               footprint
	HP                      int
	MaxHP                   int
	EN                      int
	ENMax                   int
	SP                      int
	SPMax                   int
	Pilot                   pilot
	Mech                    mech
	Skills                  []skill
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
	Debuffs                 []debuff
}

func (u *unit) alive() bool {
	return u != nil && u.HP > 0
}

func (u *unit) hasENFor(weapon weapon) bool {
	return u.EN >= weapon.ENCost
}

func (u *unit) weapon(name string) *weapon {
	for index := range u.Mech.Weapons {
		if u.Mech.Weapons[index].Name == name {
			return &u.Mech.Weapons[index]
		}
	}
	return nil
}

// decision is one activation of one unit. The contract names the payload
// 'action' and the model names it 'decision'; this package keeps the model
// name.
type decision struct {
	UnitID         string
	Kind           actionKind
	MoveTo         *cell
	TargetID       string
	Weapon         string
	Amount         *float64
	Aim            *cell
	ResponseAttack *responseAttack

	SupportDefender  string
	SupportAttackers []string
}

type responseAttack struct {
	Stance           stance
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

func (c cell) before(other cell) bool {
	if c[0] != other[0] {
		return c[0] < other[0]
	}
	return c[1] < other[1]
}

func (u unit) clone() unit {
	u.Skills = slices.Clone(u.Skills)
	for index := range u.Skills {
		u.Skills[index].Amount = cloneAmount(u.Skills[index].Amount)
	}
	u.Debuffs = slices.Clone(u.Debuffs)
	u.Ammo = maps.Clone(u.Ammo)
	u.Mech.Weapons = slices.Clone(u.Mech.Weapons)
	return u
}
