// Package def holds the data of a battle that no rule writes. A unit points at
// its mech and at its pilot, so every copy of a battle shares them.
package def

import "github.com/DeanXu2357/ggge_ai/engine/battle"

type ShapeRange struct {
	Cells     []battle.Cell
	Direction battle.Direction
}

type Weapon struct {
	Name            string
	Power           float64
	RangeMin        int
	RangeMax        int
	ENCost          int
	Accuracy        float64
	UsableAfterMove bool
	DebuffKind      *string
	DebuffMagnitude float64
	Categories      []battle.WeaponCategory
}

type MapWeapon struct {
	Name            string
	Power           float64
	ApplyShape      ShapeRange
	EffectShape     ShapeRange
	AmmoMax         int
	ENCost          int
	Accuracy        float64
	Affects         battle.MapWeaponAffects
	UsableAfterMove bool
	DebuffKind      *string
	DebuffMagnitude float64
	Categories      []battle.WeaponCategory
}

type Skill struct {
	Kind            battle.SkillKind
	Source          battle.SkillSource
	Amount          *float64
	Uses            int
	EndsActivation  bool
	UsableAfterMove bool
	Affects         battle.SkillAffects
}

type Pilot struct {
	Ranged   float64
	Melee    float64
	Awaken   float64
	Defense  float64
	Reaction float64
	SP       int
}

type Mech struct {
	HP         int
	EN         int
	Attack     float64
	Defense    float64
	Mobility   float64
	MoveRange  int
	Weapons    []Weapon
	MapWeapons []MapWeapon
}

func (w Weapon) Reaches(distance int) bool {
	return w.RangeMin <= distance && distance <= w.RangeMax
}

func (w Weapon) Debuff() string {
	if w.DebuffKind == nil {
		return ""
	}
	return *w.DebuffKind
}
