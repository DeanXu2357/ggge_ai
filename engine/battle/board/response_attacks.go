package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (b *Board) ResponseAttacks(action *protocol.Decision, defenderID string) (protocol.ResponseAttacksResponse, error) {
	decision, err := DecodeDecision(action)
	if err != nil {
		return protocol.ResponseAttacksResponse{}, err
	}
	engagement, err := b.responseAttacks(decision, defenderID)
	if err != nil {
		return protocol.ResponseAttacksResponse{}, err
	}
	return encodeEngagement(engagement), nil
}

func (b *Board) responseAttacks(action decision, defenderID string) (engagement, error) {
	defender, err := b.livingUnit(defenderID)
	if err != nil {
		return engagement{}, err
	}
	attacker, err := b.livingUnit(action.UnitID)
	if err != nil {
		return engagement{}, err
	}
	if action.Kind != actionAttack {
		return engagement{}, fmt.Errorf("an action of the kind %q asks unit %q nothing",
			action.Kind, defenderID)
	}
	out := engagement{
		Defender:        sideOptions{Unit: defender},
		Attacker:        sideOptions{Unit: attacker},
		ResponseAttacks: []responseAttackOption{},
	}
	weapon := attacker.weapon(action.Weapon)
	if weapon == nil {
		return engagement{}, fmt.Errorf("unit %q carries no weapon %q",
			attacker.ID, action.Weapon)
	}
	origin := footprintAt(attacker, strikeCell(attacker, action))
	distance := spanDistance(defender.Footprint, origin)
	if !weapon.Range.holds(distance) {
		return engagement{}, fmt.Errorf("the weapon %q of unit %q does not reach unit %q from %v",
			action.Weapon, attacker.ID, defenderID, origin.Anchor)
	}

	out.ResponseAttacks = append(out.ResponseAttacks,
		b.stanceOption(attacker, defender, weapon, stanceDodge, ""),
		b.stanceOption(attacker, defender, weapon, stanceDefend, ""))
	for index := range defender.Mech.Weapons {
		counter := &defender.Mech.Weapons[index]
		if counter.MapWeapon || !counter.CanCounter || !defender.hasENFor(*counter) {
			continue
		}
		if counter.Range.holds(distance) {
			option := b.stanceOption(attacker, defender, weapon, stanceCounter, counter.Name)
			reply := b.forecastOf(defender, attacker, counter, formula.NoDefenseMultiplier, false)
			option.Counter = &reply
			out.ResponseAttacks = append(out.ResponseAttacks, option)
		}
	}
	out.ResponseAttacks = append(out.ResponseAttacks,
		b.stanceOption(attacker, defender, weapon, stanceNone, ""))

	out.Defender.SupportDefenders = b.defendOptions(attacker, weapon,
		b.supportDefenders(defender, defender.Footprint))
	out.Defender.SupportAttackers = b.attackOptions(attacker,
		b.supportAttackers(defender, defender.Footprint, origin))
	// Which weapon counters is the pick of the defender, so the entry of a
	// unit that covers the attacker carries no forecast.
	out.Attacker.SupportDefenders = b.defendOptions(defender, nil,
		b.supportDefenders(attacker, origin))
	out.Attacker.SupportAttackers = b.attackOptions(defender,
		b.supportAttackers(attacker, origin, defender.Footprint))
	return out, nil
}

func (b *Board) stanceOption(attacker, defender *Unit, weapon *Weapon, stance stance,
	counter string) responseAttackOption {
	return responseAttackOption{
		Stance: stance,
		Weapon: counter,
		Incoming: b.forecastOf(attacker, defender, weapon,
			defenseMultiplier(stance, defender), stance == stanceDodge),
	}
}

func (b *Board) defendOptions(shooter *Unit, weapon *Weapon, units []*Unit) []supportDefendOption {
	out := make([]supportDefendOption, 0, len(units))
	for _, unit := range units {
		option := supportDefendOption{Unit: unit}
		if weapon != nil {
			option.Incoming = b.supportDefenderForecast(shooter, unit, weapon)
		}
		out = append(out, option)
	}
	return out
}

// The foe picks its stance after this answer, so the forecast of a support
// attack reads no defense.
func (b *Board) attackOptions(foe *Unit, joining []supportAttacker) []supportAttackOption {
	out := make([]supportAttackOption, 0, len(joining))
	for _, one := range joining {
		out = append(out, supportAttackOption{
			Unit:   one.Unit,
			Weapon: one.Weapon,
			Strike: b.forecastOf(one.Unit, foe, one.Weapon, formula.NoDefenseMultiplier, false),
		})
	}
	return out
}

func strikeCell(attacker *Unit, action decision) cell {
	if action.MoveTo == nil {
		return attacker.Footprint.Anchor
	}
	return *action.MoveTo
}

// The supported unit stands on 'at' after its move, so the reach of a
// support unit reads that cell and not the cell of today.
func (b *Board) supportDefenders(supported *Unit, at footprint) []*Unit {
	out := []*Unit{}
	for _, other := range b.byFaction(supported.Faction) {
		if inSupportReach(other, supported, at, other.SupportDefendCharges) {
			out = append(out, other)
		}
	}
	return out
}

type supportAttacker struct {
	Unit   *Unit
	Weapon *Weapon
}

func (b *Board) supportAttackers(supported *Unit, firing, foe footprint) []supportAttacker {
	out := []supportAttacker{}
	for _, other := range b.byFaction(supported.Faction) {
		if weapon := supportWeapon(other, supported, firing, foe); weapon != nil {
			out = append(out, supportAttacker{Unit: other, Weapon: weapon})
		}
	}
	return out
}

func supportWeapon(other, supported *Unit, firing, foe footprint) *Weapon {
	if !inSupportReach(other, supported, firing, other.SupportAttackCharges) {
		return nil
	}
	distance := spanDistance(other.Footprint, foe)
	for index := range other.Mech.Weapons {
		weapon := &other.Mech.Weapons[index]
		if !weapon.MapWeapon && other.hasENFor(*weapon) && weapon.Range.holds(distance) {
			return weapon
		}
	}
	return nil
}

func inSupportReach(other, supported *Unit, at footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		spanDistance(other.Footprint, at) <= other.Mech.MoveRange
}
