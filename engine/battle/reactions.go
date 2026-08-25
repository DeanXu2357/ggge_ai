package battle

import "fmt"

// SupportAttacker is one unit that joins the strike of the unit it supports,
// with the first weapon of that unit that reaches the foe.
type SupportAttacker struct {
	Unit   *Unit
	Weapon *Weapon
}

type ReactionOption struct {
	Stance Stance
	Weapon string
}

type SideOptions struct {
	Unit             *Unit
	SupportDefenders []*Unit
	SupportAttackers []SupportAttacker
}

type Engagement struct {
	Defender  SideOptions
	Attacker  SideOptions
	Reactions []ReactionOption
}

func (b *Board) Reactions(action Decision, defenderID string) (Engagement, error) {
	defender, err := b.livingUnit(defenderID)
	if err != nil {
		return Engagement{}, err
	}
	attacker, err := b.livingUnit(action.UnitID)
	if err != nil {
		return Engagement{}, err
	}
	if action.Kind != ActionAttack {
		return Engagement{}, fmt.Errorf("an action of the kind %q asks unit %q nothing",
			action.Kind, defenderID)
	}
	out := Engagement{
		Defender:  SideOptions{Unit: defender},
		Attacker:  SideOptions{Unit: attacker},
		Reactions: []ReactionOption{},
	}
	weapon := attacker.Weapon(action.Weapon)
	if weapon == nil {
		return Engagement{}, fmt.Errorf("unit %q carries no weapon %q",
			attacker.ID, action.Weapon)
	}
	origin := footprintAt(attacker, strikeCell(attacker, action))
	distance := SpanDistance(defender.Footprint, origin)
	if !weapon.Range.Holds(distance) {
		return Engagement{}, fmt.Errorf("the weapon %q of unit %q does not reach unit %q from %v",
			action.Weapon, attacker.ID, defenderID, origin.Anchor)
	}

	out.Reactions = append(out.Reactions,
		ReactionOption{Stance: StanceDodge},
		ReactionOption{Stance: StanceDefend})
	for index := range defender.Weapons {
		counter := &defender.Weapons[index]
		if counter.MapWeapon || !counter.CanCounter || !defender.HasENFor(*counter) {
			continue
		}
		if counter.Range.Holds(distance) {
			out.Reactions = append(out.Reactions,
				ReactionOption{Stance: StanceCounter, Weapon: counter.Name})
		}
	}
	out.Reactions = append(out.Reactions, ReactionOption{Stance: StanceNone})

	out.Defender.SupportDefenders = b.SupportDefenders(defender, defender.Footprint)
	out.Defender.SupportAttackers = b.SupportAttackers(defender, defender.Footprint, origin)
	out.Attacker.SupportDefenders = b.SupportDefenders(attacker, origin)
	out.Attacker.SupportAttackers = b.SupportAttackers(attacker, origin, defender.Footprint)
	return out, nil
}

func strikeCell(attacker *Unit, action Decision) Cell {
	if action.MoveTo == nil {
		return attacker.Footprint.Anchor
	}
	return *action.MoveTo
}

// SupportDefenders gives the units that can take a strike for the supported
// unit while it stands on 'at'. The supported unit stands on 'at' after its
// move, so the reach of a support unit reads that cell and not the cell of
// today.
func (b *Board) SupportDefenders(supported *Unit, at Footprint) []*Unit {
	out := []*Unit{}
	for _, other := range b.ByFaction(supported.Faction) {
		if inSupportReach(other, supported, at, other.SupportDefendCharges) {
			out = append(out, other)
		}
	}
	return out
}

// SupportAttackers gives the units that can join a strike of the supported unit
// against a foe on 'foe', each one with the weapon it fires. The supported unit
// fires from 'firing', which is its anchor after its move.
func (b *Board) SupportAttackers(supported *Unit, firing, foe Footprint) []SupportAttacker {
	out := []SupportAttacker{}
	for _, other := range b.ByFaction(supported.Faction) {
		if weapon := supportWeapon(other, supported, firing, foe); weapon != nil {
			out = append(out, SupportAttacker{Unit: other, Weapon: weapon})
		}
	}
	return out
}

func supportWeapon(other, supported *Unit, firing, foe Footprint) *Weapon {
	if !inSupportReach(other, supported, firing, other.SupportAttackCharges) {
		return nil
	}
	distance := SpanDistance(other.Footprint, foe)
	for index := range other.Weapons {
		weapon := &other.Weapons[index]
		if !weapon.MapWeapon && other.HasENFor(*weapon) && weapon.Range.Holds(distance) {
			return weapon
		}
	}
	return nil
}

// The support reach of a unit is the move range of that unit
// (docs/reference/combat-formulas.md, case 14).
func inSupportReach(other, supported *Unit, at Footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		SpanDistance(other.Footprint, at) <= other.MoveRange
}
