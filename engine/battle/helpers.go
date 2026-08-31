package battle

import (
	"maps"
	"slices"
)

type Terrain string

const (
	TerrainSpace       Terrain = "space"
	TerrainAtmospheric Terrain = "atmospheric"
	TerrainGround      Terrain = "ground"
	TerrainSurface     Terrain = "surface"
	TerrainUnderwater  Terrain = "underwater"
)

type WeaponCategory string

const (
	WeaponCategoryRanged WeaponCategory = "ranged"
	WeaponCategoryMelee  WeaponCategory = "melee"
	WeaponCategoryAwaken WeaponCategory = "awaken"
)

var WeaponCategories = [...]WeaponCategory{
	WeaponCategoryRanged, WeaponCategoryMelee, WeaponCategoryAwaken,
}

// An empty terrain is the terrain that a state leaves out, and it reads as
// space.
var terrains = map[Terrain]bool{
	"":                 true,
	TerrainSpace:       true,
	TerrainAtmospheric: true,
	TerrainGround:      true,
	TerrainSurface:     true,
	TerrainUnderwater:  true,
}

var weaponCategories = map[WeaponCategory]bool{
	WeaponCategoryRanged: true,
	WeaponCategoryMelee:  true,
	WeaponCategoryAwaken: true,
}

func (t *Terrain) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, t, terrains, "terrain")
}

func (c *WeaponCategory) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, c, weaponCategories, "weapon category")
}

func (c Cell) Before(other Cell) bool {
	if c[0] != other[0] {
		return c[0] < other[0]
	}
	return c[1] < other[1]
}

// Footprint carries no JSON tag: the wire holds the anchor and the size as
// two fields of the unit.
type Footprint struct {
	Anchor Cell
	Size   Cell
}

func (f Footprint) Within(bounds Bounds) bool {
	high := Cell{f.Anchor[0] + f.Size[0] - 1, f.Anchor[1] + f.Size[1] - 1}
	return bounds[0][0] <= f.Anchor[0] && high[0] <= bounds[1][0] &&
		bounds[0][1] <= f.Anchor[1] && high[1] <= bounds[1][1]
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

// A size of zero on an axis is a unit that covers one cell on that axis.
func (u *Unit) Footprint() Footprint {
	out := Footprint{Anchor: u.Pos, Size: u.Size}
	for axis := range out.Size {
		if out.Size[axis] == 0 {
			out.Size[axis] = 1
		}
	}
	return out
}

// PhaseOrder is the rotation of the sides inside one turn.
var PhaseOrder = [...]Faction{FactionAlly, FactionThirdParty, FactionEnemy}

func (f Faction) Opposing() Faction {
	if f == FactionAlly {
		return FactionEnemy
	}
	return FactionAlly
}

// The weapons of a mech are never written after the decode, so the clone
// shares them with the state it comes from.
func (s *BattleState) Clone() BattleState {
	out := *s
	if s.Bounds != nil {
		bounds := *s.Bounds
		out.Bounds = &bounds
	}
	out.Units = make([]Unit, len(s.Units))
	for index := range s.Units {
		out.Units[index] = cloneUnit(s.Units[index])
	}
	out.TerrainCells = slices.Clone(s.TerrainCells)
	out.PendingEvents = slices.Clone(s.PendingEvents)
	out.FiredEvents = slices.Clone(s.FiredEvents)
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
