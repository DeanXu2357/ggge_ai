package battle

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var factions = map[protocol.Faction]Faction{
	protocol.FactionAlly:       FactionAlly,
	protocol.FactionEnemy:      FactionEnemy,
	protocol.FactionThirdParty: FactionThirdParty,
}

func DecodeState(state *protocol.BattleState) (*Board, error) {
	if state == nil {
		return nil, fmt.Errorf("the payload carries no state")
	}
	bounds, err := decodeBounds(state.Bounds)
	if err != nil {
		return nil, err
	}
	units, err := decodeUnits(state.Units)
	if err != nil {
		return nil, err
	}
	board, err := NewBoard(bounds, units)
	if err != nil {
		return nil, err
	}
	if board.DefaultTerrain, err = decodeTerrain(state.Terrain); err != nil {
		return nil, err
	}
	if board.TerrainCells, err = decodeTerrainCells(state.TerrainCells); err != nil {
		return nil, err
	}
	return board, nil
}

func decodeTerrain(name string) (Terrain, error) {
	if name == "" {
		return TerrainSpace, nil
	}
	return ParseTerrain(name)
}

func decodeTerrainCells(cells []protocol.TerrainCell) (map[Cell]Terrain, error) {
	if len(cells) == 0 {
		return nil, nil
	}
	out := make(map[Cell]Terrain, len(cells))
	for _, entry := range cells {
		kind, err := ParseTerrain(entry.Terrain)
		if err != nil {
			return nil, fmt.Errorf("the cell %v carries a terrain outside the contract: %w",
				entry.Cell, err)
		}
		out[DecodeCell(entry.Cell)] = kind
	}
	return out, nil
}

func decodeUnits(units []protocol.Unit) ([]Unit, error) {
	if units == nil {
		return nil, nil
	}
	out := make([]Unit, 0, len(units))
	for index := range units {
		unit, err := decodeUnit(&units[index])
		if err != nil {
			return nil, err
		}
		out = append(out, unit)
	}
	return out, nil
}

func DecodeCell(cell protocol.Cell) Cell {
	return Cell{cell[0], cell[1]}
}

func EncodeCell(cell Cell) protocol.Cell {
	return protocol.Cell{cell[0], cell[1]}
}

func EncodeCells(cells []Cell) []protocol.Cell {
	out := make([]protocol.Cell, 0, len(cells))
	for _, cell := range cells {
		out = append(out, EncodeCell(cell))
	}
	return out
}

func decodeUnit(unit *protocol.Unit) (Unit, error) {
	faction, known := factions[unit.Faction]
	if !known {
		return Unit{}, fmt.Errorf("unit %q carries the faction %q, which is not in the contract",
			unit.UnitID, unit.Faction)
	}
	footprint, err := decodeFootprint(unit)
	if err != nil {
		return Unit{}, err
	}
	out := Unit{
		ID:        unit.UnitID,
		Faction:   faction,
		Footprint: footprint,
		HP:        unit.HP,
		EN:        unit.EN,
		Pilot: Pilot{
			Attack:   unit.PilotAttack,
			Defense:  unit.PilotDefense,
			Reaction: unit.Reaction,
		},
		Mech: Mech{
			Attack:   unit.UnitAttack,
			Defense:  unit.UnitDefense,
			Mobility: unit.Mobility,
		},
		MoveRange:            unit.MoveRange,
		SupportDefendCharges: unit.SupportDefendCharges,
		SupportAttackCharges: unit.SupportAttackCharges,
	}
	if unit.Weapons != nil {
		out.Weapons = make([]Weapon, 0, len(unit.Weapons))
		for index := range unit.Weapons {
			weapon, err := decodeWeapon(&unit.Weapons[index])
			if err != nil {
				return Unit{}, fmt.Errorf("unit %q: %w", unit.UnitID, err)
			}
			out.Weapons = append(out.Weapons, weapon)
		}
	}
	return out, nil
}

func decodeWeapon(weapon *protocol.Weapon) (Weapon, error) {
	out := Weapon{
		Name:      weapon.Name,
		Range:     RadiusRange{Min: weapon.RangeMin, Max: weapon.RangeMax},
		ENCost:    weapon.ENCost,
		MapWeapon: weapon.MapWeapon,
	}
	for name, scale := range weapon.TerrainDamage {
		kind, err := ParseTerrain(name)
		if err != nil {
			return Weapon{}, fmt.Errorf("weapon %q: %w", weapon.Name, err)
		}
		if out.TerrainDamage == nil {
			out.TerrainDamage = make(map[Terrain]float64, len(weapon.TerrainDamage))
		}
		out.TerrainDamage[kind] = scale
	}
	for _, name := range weapon.UnusableIn {
		kind, err := ParseTerrain(name)
		if err != nil {
			return Weapon{}, fmt.Errorf("weapon %q: %w", weapon.Name, err)
		}
		if out.UnusableIn == nil {
			out.UnusableIn = make(TerrainSet, len(weapon.UnusableIn))
		}
		out.UnusableIn[kind] = true
	}
	return out, nil
}

func decodeFootprint(unit *protocol.Unit) (Footprint, error) {
	size := Size{unit.Size[0], unit.Size[1]}
	for axis := range size {
		if size[axis] < 0 {
			return Footprint{}, fmt.Errorf("unit %q carries the size %v", unit.UnitID, unit.Size)
		}
		if size[axis] == 0 {
			size[axis] = 1
		}
	}
	return Footprint{Anchor: DecodeCell(unit.Pos), Size: size}, nil
}

func decodeBounds(bounds *protocol.Bounds) (Bounds, error) {
	if bounds == nil {
		return Bounds{}, fmt.Errorf("the state carries no bounds")
	}
	return Bounds{Low: DecodeCell(bounds[0]), High: DecodeCell(bounds[1])}, nil
}
