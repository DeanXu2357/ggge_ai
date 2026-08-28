package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func (b *Board) ResponseAttacks(action battle.Decision, defenderID string) (battle.Engagement, error) {
	defender, err := b.livingUnit(defenderID)
	if err != nil {
		return battle.Engagement{}, err
	}
	attacker, err := b.livingUnit(action.UnitID)
	if err != nil {
		return battle.Engagement{}, err
	}
	if action.Kind != battle.ActionAttack {
		return battle.Engagement{}, fmt.Errorf("an action of the kind %q asks unit %q nothing",
			action.Kind, defenderID)
	}
	out := battle.Engagement{
		Defender:        battle.SideOptions{Unit: defender},
		Attacker:        battle.SideOptions{Unit: attacker},
		ResponseAttacks: []battle.ResponseAttackOption{},
	}
	weapon := attacker.Weapon(action.Weapon)
	if weapon == nil {
		return battle.Engagement{}, fmt.Errorf("unit %q carries no weapon %q",
			attacker.ID, action.Weapon)
	}
	origin := footprintAt(attacker, strikeCell(attacker, action))
	distance := SpanDistance(defender.Footprint, origin)
	if !weapon.Range.Holds(distance) {
		return battle.Engagement{}, fmt.Errorf("the weapon %q of unit %q does not reach unit %q from %v",
			action.Weapon, attacker.ID, defenderID, origin.Anchor)
	}

	out.ResponseAttacks = append(out.ResponseAttacks,
		b.stanceOption(attacker, defender, weapon, battle.StanceDodge, ""),
		b.stanceOption(attacker, defender, weapon, battle.StanceDefend, ""))
	for index := range defender.Mech.Weapons {
		counter := &defender.Mech.Weapons[index]
		if counter.MapWeapon || !counter.CanCounter || !defender.HasENFor(*counter) {
			continue
		}
		if counter.Range.Holds(distance) {
			option := b.stanceOption(attacker, defender, weapon, battle.StanceCounter, counter.Name)
			reply := b.forecastOf(defender, attacker, counter, NoDefenseMultiplier, false)
			option.Counter = &reply
			out.ResponseAttacks = append(out.ResponseAttacks, option)
		}
	}
	out.ResponseAttacks = append(out.ResponseAttacks,
		b.stanceOption(attacker, defender, weapon, battle.StanceNone, ""))

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

func (b *Board) stanceOption(attacker, defender *battle.Unit, weapon *battle.Weapon, stance battle.Stance,
	counter string) battle.ResponseAttackOption {
	return battle.ResponseAttackOption{
		Stance: stance,
		Weapon: counter,
		Incoming: b.forecastOf(attacker, defender, weapon,
			StanceMultiplier(stance, defender), stance == battle.StanceDodge),
	}
}

func (b *Board) defendOptions(shooter *battle.Unit, weapon *battle.Weapon, units []*battle.Unit) []battle.SupportDefendOption {
	out := make([]battle.SupportDefendOption, 0, len(units))
	for _, unit := range units {
		option := battle.SupportDefendOption{Unit: unit}
		if weapon != nil {
			option.Incoming = b.supportDefenderForecast(shooter, unit, weapon)
		}
		out = append(out, option)
	}
	return out
}

// The foe picks its stance after this answer, so the forecast of a support
// attack reads no defense.
func (b *Board) attackOptions(foe *battle.Unit, joining []SupportAttacker) []battle.SupportAttackOption {
	out := make([]battle.SupportAttackOption, 0, len(joining))
	for _, one := range joining {
		out = append(out, battle.SupportAttackOption{
			Unit:   one.Unit,
			Weapon: one.Weapon,
			Strike: b.forecastOf(one.Unit, foe, one.Weapon, NoDefenseMultiplier, false),
		})
	}
	return out
}

func strikeCell(attacker *battle.Unit, action battle.Decision) battle.Cell {
	if action.MoveTo == nil {
		return attacker.Footprint.Anchor
	}
	return *action.MoveTo
}

// The supported unit stands on 'at' after its move, so the reach of a
// support unit reads that cell and not the cell of today.
func (b *Board) supportDefenders(supported *battle.Unit, at battle.Footprint) []*battle.Unit {
	out := []*battle.Unit{}
	for _, other := range b.byFaction(supported.Faction) {
		if inSupportReach(other, supported, at, other.SupportDefendCharges) {
			out = append(out, other)
		}
	}
	return out
}

type SupportAttacker struct {
	Unit   *battle.Unit
	Weapon *battle.Weapon
}

func (b *Board) supportAttackers(supported *battle.Unit, firing, foe battle.Footprint) []SupportAttacker {
	out := []SupportAttacker{}
	for _, other := range b.byFaction(supported.Faction) {
		if weapon := supportWeapon(other, supported, firing, foe); weapon != nil {
			out = append(out, SupportAttacker{Unit: other, Weapon: weapon})
		}
	}
	return out
}

func supportWeapon(other, supported *battle.Unit, firing, foe battle.Footprint) *battle.Weapon {
	if !inSupportReach(other, supported, firing, other.SupportAttackCharges) {
		return nil
	}
	distance := SpanDistance(other.Footprint, foe)
	for index := range other.Mech.Weapons {
		weapon := &other.Mech.Weapons[index]
		if !weapon.MapWeapon && other.HasENFor(*weapon) && weapon.Range.Holds(distance) {
			return weapon
		}
	}
	return nil
}

func inSupportReach(other, supported *battle.Unit, at battle.Footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		SpanDistance(other.Footprint, at) <= other.Mech.MoveRange
}
