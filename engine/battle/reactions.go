package battle

import "fmt"

type SupportAttacker struct {
	Unit   *Unit
	Weapon *Weapon
}

type ReactionOption struct {
	Stance   Stance
	Weapon   string
	Incoming Forecast
	Counter  *Forecast
}

type SupportDefendOption struct {
	Unit     *Unit
	Incoming Forecast
}

type SupportAttackOption struct {
	Unit   *Unit
	Weapon *Weapon
	Strike Forecast
}

type SideOptions struct {
	Unit             *Unit
	SupportDefenders []SupportDefendOption
	SupportAttackers []SupportAttackOption
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
		b.stanceOption(attacker, defender, weapon, StanceDodge, ""),
		b.stanceOption(attacker, defender, weapon, StanceDefend, ""))
	for index := range defender.Mech.Weapons {
		counter := &defender.Mech.Weapons[index]
		if counter.MapWeapon || !counter.CanCounter || !defender.HasENFor(*counter) {
			continue
		}
		if counter.Range.Holds(distance) {
			option := b.stanceOption(attacker, defender, weapon, StanceCounter, counter.Name)
			reply := b.forecastOf(defender, attacker, counter, NoDefenseMultiplier, false)
			option.Counter = &reply
			out.Reactions = append(out.Reactions, option)
		}
	}
	out.Reactions = append(out.Reactions,
		b.stanceOption(attacker, defender, weapon, StanceNone, ""))

	out.Defender.SupportDefenders = b.defendOptions(attacker, weapon,
		b.SupportDefenders(defender, defender.Footprint))
	out.Defender.SupportAttackers = b.attackOptions(attacker,
		b.SupportAttackers(defender, defender.Footprint, origin))
	// Which weapon counters is the pick of the defender, so the entry of a
	// unit that covers the attacker carries no forecast.
	out.Attacker.SupportDefenders = b.defendOptions(defender, nil,
		b.SupportDefenders(attacker, origin))
	out.Attacker.SupportAttackers = b.attackOptions(defender,
		b.SupportAttackers(attacker, origin, defender.Footprint))
	return out, nil
}

func (b *Board) stanceOption(attacker, defender *Unit, weapon *Weapon, stance Stance,
	counter string) ReactionOption {
	return ReactionOption{
		Stance: stance,
		Weapon: counter,
		Incoming: b.forecastOf(attacker, defender, weapon,
			StanceMultiplier(stance, defender), stance == StanceDodge),
	}
}

func (b *Board) defendOptions(shooter *Unit, weapon *Weapon, units []*Unit) []SupportDefendOption {
	out := make([]SupportDefendOption, 0, len(units))
	for _, unit := range units {
		option := SupportDefendOption{Unit: unit}
		if weapon != nil {
			option.Incoming = b.supportDefenderForecast(shooter, unit, weapon)
		}
		out = append(out, option)
	}
	return out
}

// The foe picks its stance after this answer, so the forecast of a support
// attack reads no defense.
func (b *Board) attackOptions(foe *Unit, joining []SupportAttacker) []SupportAttackOption {
	out := make([]SupportAttackOption, 0, len(joining))
	for _, one := range joining {
		out = append(out, SupportAttackOption{
			Unit:   one.Unit,
			Weapon: one.Weapon,
			Strike: b.forecastOf(one.Unit, foe, one.Weapon, NoDefenseMultiplier, false),
		})
	}
	return out
}

func strikeCell(attacker *Unit, action Decision) Cell {
	if action.MoveTo == nil {
		return attacker.Footprint.Anchor
	}
	return *action.MoveTo
}

// The supported unit stands on 'at' after its move, so the reach of a
// support unit reads that cell and not the cell of today.
func (b *Board) SupportDefenders(supported *Unit, at Footprint) []*Unit {
	out := []*Unit{}
	for _, other := range b.ByFaction(supported.Faction) {
		if inSupportReach(other, supported, at, other.SupportDefendCharges) {
			out = append(out, other)
		}
	}
	return out
}

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
	for index := range other.Mech.Weapons {
		weapon := &other.Mech.Weapons[index]
		if !weapon.MapWeapon && other.HasENFor(*weapon) && weapon.Range.Holds(distance) {
			return weapon
		}
	}
	return nil
}

func inSupportReach(other, supported *Unit, at Footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		SpanDistance(other.Footprint, at) <= other.Mech.MoveRange
}
