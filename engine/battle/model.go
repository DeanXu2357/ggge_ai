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

type Weapon struct {
	Name      string
	Range     RadiusRange
	ENCost    int
	MapWeapon bool
}

type Unit struct {
	ID                   string
	Faction              Faction
	Footprint            Footprint
	HP                   int
	EN                   int
	MoveRange            int
	Weapons              []Weapon
	SupportDefendCharges int
	SupportAttackCharges int
}

func (u *Unit) Alive() bool {
	return u != nil && u.HP > 0
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
	Bounds Bounds
	Units  []Unit
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
