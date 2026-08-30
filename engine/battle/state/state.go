package state

import (
	"maps"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

type Cell [2]int

func (c Cell) Before(other Cell) bool {
	if c[0] != other[0] {
		return c[0] < other[0]
	}
	return c[1] < other[1]
}

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

type Faction string

const (
	FactionAlly       Faction = "ally"
	FactionEnemy      Faction = "enemy"
	FactionThirdParty Faction = "third_party"
)

// PhaseOrder is the rotation of the sides inside one turn.
var PhaseOrder = [...]Faction{FactionAlly, FactionThirdParty, FactionEnemy}

func (f Faction) Opposing() Faction {
	if f == FactionAlly {
		return FactionEnemy
	}
	return FactionAlly
}

type Terrain int

const (
	TerrainSpace Terrain = iota
	TerrainAtmospheric
	TerrainGround
	TerrainSurface
	TerrainUnderwater
)

var Names = [...]string{
	TerrainSpace:       "space",
	TerrainAtmospheric: "atmospheric",
	TerrainGround:      "ground",
	TerrainSurface:     "surface",
	TerrainUnderwater:  "underwater",
}

type Debuff struct {
	Kind         string
	Magnitude    float64
	AppliedPhase int
}

// SkillKind names one skill. The set is open until issue #81 says what a
// skill does. It is not an action of a unit.
type SkillKind string

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
	Range           def.RadiusRange
	Blast           int
	Affects         SkillAffects
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
	Pilot                   *def.Pilot
	Mech                    *def.Mech
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

// A destroyed unit keeps its place on the board with no hit points left, and
// a lookup that finds nothing answers with a nil unit.
func (u *Unit) Alive() bool {
	return u != nil && u.HP > 0
}

type Board struct {
	Bounds         Bounds
	Units          []Unit
	Phase          Faction
	Turn           int
	DefaultTerrain Terrain
	TerrainCells   map[Cell]Terrain
}

func (b *Board) Unit(id string) *Unit {
	for index := range b.Units {
		if b.Units[index].ID == id {
			return &b.Units[index]
		}
	}
	return nil
}

// PhaseIndex counts the phases from the first phase of the first turn. A
// debuff carries the index of the phase that applied it.
func (b *Board) PhaseIndex() int {
	for index, faction := range PhaseOrder {
		if faction == b.Phase {
			return b.Turn*len(PhaseOrder) + index
		}
	}
	return b.Turn * len(PhaseOrder)
}

// The definitions are immutable after the decode, so the clone shares the mech
// and the pilot of each unit with the board it comes from.
func (b *Board) Clone() Board {
	out := *b
	out.Units = make([]Unit, len(b.Units))
	for index := range b.Units {
		out.Units[index] = cloneUnit(b.Units[index])
	}
	out.TerrainCells = maps.Clone(b.TerrainCells)
	return out
}

func cloneUnit(unit Unit) Unit {
	unit.Skills = slices.Clone(unit.Skills)
	for index := range unit.Skills {
		unit.Skills[index].Amount = CloneAmount(unit.Skills[index].Amount)
	}
	unit.Debuffs = slices.Clone(unit.Debuffs)
	unit.Ammo = maps.Clone(unit.Ammo)
	return unit
}

func CloneAmount(amount *float64) *float64 {
	if amount == nil {
		return nil
	}
	out := *amount
	return &out
}
