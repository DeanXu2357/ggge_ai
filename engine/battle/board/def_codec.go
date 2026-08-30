package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func parseWeaponCategory(name string) (def.WeaponCategory, error) {
	for _, known := range def.WeaponCategories {
		if string(known) == name {
			return known, nil
		}
	}
	return "", fmt.Errorf("the weapon category %q is not in the contract", name)
}

func decodeMech(unitID string, wire *protocol.Mech) (*def.Mech, error) {
	out := &def.Mech{
		HP:        wire.HP,
		EN:        wire.EN,
		Attack:    wire.Attack,
		Defense:   wire.Defense,
		Mobility:  wire.Mobility,
		MoveRange: wire.MoveRange,
	}
	weapons, err := decodeWeapons(unitID, wire.Weapons)
	if err != nil {
		return nil, err
	}
	out.Weapons = weapons
	return out, nil
}

func decodePilot(wire *protocol.Pilot) *def.Pilot {
	return &def.Pilot{
		Ranged:   wire.Ranged,
		Melee:    wire.Melee,
		Awaken:   wire.Awaken,
		Defense:  wire.Defense,
		Reaction: wire.Reaction,
		SP:       wire.SP,
	}
}

func decodeWeapons(unitID string, weapons []protocol.Weapon) ([]def.Weapon, error) {
	if weapons == nil {
		return nil, nil
	}
	out := make([]def.Weapon, 0, len(weapons))
	for index := range weapons {
		weapon, err := decodeWeapon(&weapons[index])
		if err != nil {
			return nil, fmt.Errorf("unit %q: %w", unitID, err)
		}
		out = append(out, weapon)
	}
	return out, nil
}

func decodeWeapon(wire *protocol.Weapon) (def.Weapon, error) {
	out := def.Weapon{
		Name:            wire.Name,
		Power:           wire.Power,
		Range:           def.RadiusRange{Min: wire.RangeMin, Max: wire.RangeMax},
		ENCost:          wire.ENCost,
		Accuracy:        wire.Accuracy,
		MapWeapon:       wire.MapWeapon,
		UsableAfterMove: wire.UsableAfterMove,
		DebuffMagnitude: wire.DebuffMagnitude,
	}
	if wire.DebuffKind != nil {
		out.DebuffKind = *wire.DebuffKind
	}
	for _, name := range wire.Categories {
		category, err := parseWeaponCategory(name)
		if err != nil {
			return def.Weapon{}, fmt.Errorf("the weapon %q carries %w", wire.Name, err)
		}
		out.Categories = append(out.Categories, category)
	}
	return out, nil
}

func encodeMech(mech *def.Mech) protocol.Mech {
	out := protocol.Mech{
		HP:        mech.HP,
		EN:        mech.EN,
		Attack:    mech.Attack,
		Defense:   mech.Defense,
		Mobility:  mech.Mobility,
		MoveRange: mech.MoveRange,
		Weapons:   make([]protocol.Weapon, 0, len(mech.Weapons)),
	}
	for _, weapon := range mech.Weapons {
		out.Weapons = append(out.Weapons, encodeWeapon(weapon))
	}
	return out
}

func encodePilot(pilot *def.Pilot) protocol.Pilot {
	return protocol.Pilot{
		Ranged:   pilot.Ranged,
		Melee:    pilot.Melee,
		Awaken:   pilot.Awaken,
		Defense:  pilot.Defense,
		Reaction: pilot.Reaction,
		SP:       pilot.SP,
	}
}

func encodeWeapon(weapon def.Weapon) protocol.Weapon {
	out := protocol.Weapon{
		Name:            weapon.Name,
		Power:           weapon.Power,
		RangeMin:        weapon.Range.Min,
		RangeMax:        weapon.Range.Max,
		ENCost:          weapon.ENCost,
		Accuracy:        weapon.Accuracy,
		MapWeapon:       weapon.MapWeapon,
		UsableAfterMove: weapon.UsableAfterMove,
		DebuffMagnitude: weapon.DebuffMagnitude,
	}
	if weapon.DebuffKind != "" {
		kind := weapon.DebuffKind
		out.DebuffKind = &kind
	}
	for _, category := range weapon.Categories {
		out.Categories = append(out.Categories, string(category))
	}
	return out
}
