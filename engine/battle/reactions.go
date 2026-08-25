package battle

import "fmt"

// SupportAttacker is one unit that joins the strike of the unit it supports,
// with the first weapon of that unit that reaches the foe.
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

// SupportDefendOption is one unit that can take the strike for the side, with
// what the strike does to it.
type SupportDefendOption struct {
	Unit     *Unit
	Incoming Forecast
}

// SupportAttackOption is one unit that can join the strike of the side, with
// what its own shot does to the foe.
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
	for index := range defender.Weapons {
		counter := &defender.Weapons[index]
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
	// A unit that covers the attacker takes the counter, and which weapon
	// counters is the pick of the defender, so its entry carries no forecast.
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
			b.Rules.StanceMultiplier(stance, defender), stance == StanceDodge),
	}
}

// The unit that a support defender covers takes the strike of 'shooter'. The
// attacker shoots at the interceptors of the defending side, and the counter of
// the defender shoots at the interceptors of the attacking side.
func (b *Board) defendOptions(shooter *Unit, weapon *Weapon, units []*Unit) []SupportDefendOption {
	out := make([]SupportDefendOption, 0, len(units))
	for _, unit := range units {
		option := SupportDefendOption{Unit: unit}
		if weapon != nil {
			option.Incoming = b.interceptionForecast(shooter, unit, weapon)
		}
		out = append(out, option)
	}
	return out
}

// A support attacker fires at the foe of the unit it supports, and no stance of
// that foe stands beside the entry, so the forecast reads no defense.
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
