package battle

import "fmt"

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
type Weapon struct {
	Name          string
	Range         RadiusRange
	ENCost        int
	Accuracy      float64
	MapWeapon     bool
	TerrainDamage map[Terrain]float64
	UnusableIn    TerrainSet
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
	ID                   string
	Faction              Faction
	Footprint            Footprint
	HP                   int
	EN                   int
	Pilot                Pilot
	Mech                 Mech
	MoveRange            int
	Weapons              []Weapon
	SupportDefendCharges int
	SupportAttackCharges int
}

func (u *Unit) Alive() bool {
	return u != nil && u.HP > 0
}

func (u *Unit) HasENFor(weapon Weapon) bool {
	return u.EN >= weapon.ENCost
}

func NewBoard(bounds Bounds, units []Unit) (*Board, error) {
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
	return &Board{Bounds: bounds, Units: units}, nil
}

type Board struct {
	Bounds         Bounds
	Units          []Unit
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

func (b *Board) Unit(id string) *Unit {
	for index := range b.Units {
		if b.Units[index].ID == id {
			return &b.Units[index]
		}
	}
	return nil
}

func (b *Board) Roster() []Unit {
	panic("to be implemented")
}

func (b *Board) ReachableCells(unitID string) ([]Cell, error) {
	unit := b.Unit(unitID)
	if unit == nil {
		return nil, fmt.Errorf("the board holds no unit %q", unitID)
	}
	anchors := ReachableAnchors(unit.Footprint, unit.MoveRange,
		b.BlockingCells(unit), b.OccupiedCells(unit), b.Bounds)
	return SortedCells(anchors), nil
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
