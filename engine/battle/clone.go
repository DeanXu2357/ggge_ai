package battle

import (
	"maps"
	"slices"
)

func (b *Board) Clone() *Board {
	out := *b
	out.Units = make([]Unit, len(b.Units))
	for index := range b.Units {
		out.Units[index] = b.Units[index].Clone()
	}
	out.TerrainCells = maps.Clone(b.TerrainCells)
	return &out
}

func (u Unit) Clone() Unit {
	u.Weapons = slices.Clone(u.Weapons)
	u.Skills = slices.Clone(u.Skills)
	for index := range u.Skills {
		u.Skills[index].Amount = cloneAmount(u.Skills[index].Amount)
	}
	u.Debuffs = slices.Clone(u.Debuffs)
	u.Ammo = maps.Clone(u.Ammo)
	u.Mech.Weapons = slices.Clone(u.Mech.Weapons)
	return u
}
