package engagement

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// Menu answers the question 'response_attacks' with the eligibility helpers
// that Prepare reads, so the offer and the check never part.
func Menu(board *state.Board, decision Decision, defenderID string) (Options, error) {
	defender, err := livingUnit(board, defenderID)
	if err != nil {
		return Options{}, err
	}
	attacker, err := livingUnit(board, decision.UnitID)
	if err != nil {
		return Options{}, err
	}
	if decision.Kind != ActionAttack {
		return Options{}, fmt.Errorf("an action of the kind %q asks unit %q nothing",
			decision.Kind, defenderID)
	}
	out := Options{
		Defender:        SideOptions{Unit: defender},
		Attacker:        SideOptions{Unit: attacker},
		ResponseAttacks: []ResponseAttackOption{},
	}
	weapon := weaponOf(attacker, decision.Weapon)
	if weapon == nil {
		return Options{}, fmt.Errorf("unit %q carries no weapon %q",
			attacker.ID, decision.Weapon)
	}
	origin := geometry.FootprintAt(attacker, strikeCell(attacker, decision))
	distance := geometry.Distance(defender.Footprint, origin)
	if !weapon.Range.Holds(distance) {
		return Options{}, fmt.Errorf("the weapon %q of unit %q does not reach unit %q from %v",
			decision.Weapon, attacker.ID, defenderID, origin.Anchor)
	}

	out.ResponseAttacks = append(out.ResponseAttacks,
		stanceOption(attacker, defender, weapon, StanceDodge, ""),
		stanceOption(attacker, defender, weapon, StanceDefend, ""))
	for index := range defender.Mech.Weapons {
		counter := &defender.Mech.Weapons[index]
		if !counterFits(defender, counter, distance) {
			continue
		}
		option := stanceOption(attacker, defender, weapon, StanceCounter, counter.Name)
		reply := forecastOf(defender, attacker, counter, formula.NoDefenseMultiplier, false)
		option.Counter = &reply
		out.ResponseAttacks = append(out.ResponseAttacks, option)
	}
	out.ResponseAttacks = append(out.ResponseAttacks,
		stanceOption(attacker, defender, weapon, StanceNone, ""))

	out.Defender.SupportDefenders = defendOptions(attacker, weapon,
		supportDefenders(board, defender, defender.Footprint))
	out.Defender.SupportAttackers = attackOptions(attacker,
		supportAttackers(board, defender, defender.Footprint, origin))
	// Which weapon counters is the pick of the defender, so the entry of a
	// unit that covers the attacker carries no forecast.
	out.Attacker.SupportDefenders = defendOptions(defender, nil,
		supportDefenders(board, attacker, origin))
	out.Attacker.SupportAttackers = attackOptions(defender,
		supportAttackers(board, attacker, origin, defender.Footprint))
	return out, nil
}

func stanceOption(attacker, defender *state.Unit, weapon *def.Weapon, stance Stance,
	counter string) ResponseAttackOption {
	return ResponseAttackOption{
		Stance: stance,
		Weapon: counter,
		Incoming: forecastOf(attacker, defender, weapon,
			defenseMultiplier(stance, defender), stance == StanceDodge),
	}
}

func defendOptions(shooter *state.Unit, weapon *def.Weapon, units []*state.Unit) []SupportDefendOption {
	out := make([]SupportDefendOption, 0, len(units))
	for _, unit := range units {
		option := SupportDefendOption{Unit: unit}
		if weapon != nil {
			option.Incoming = supportDefenderForecast(shooter, unit, weapon)
		}
		out = append(out, option)
	}
	return out
}

// The foe picks its stance after this answer, so the forecast of a support
// attack reads no defense.
func attackOptions(foe *state.Unit, joining []supportAttacker) []SupportAttackOption {
	out := make([]SupportAttackOption, 0, len(joining))
	for _, one := range joining {
		out = append(out, SupportAttackOption{
			Unit:   one.Unit,
			Weapon: one.Weapon,
			Strike: forecastOf(one.Unit, foe, one.Weapon, formula.NoDefenseMultiplier, false),
		})
	}
	return out
}

func strikeCell(attacker *state.Unit, decision Decision) state.Cell {
	if decision.MoveTo == nil {
		return attacker.Footprint.Anchor
	}
	return *decision.MoveTo
}
