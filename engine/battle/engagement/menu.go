package engagement

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
)

// Menu answers the question 'response_attacks' from the plan that 'act' would
// run, so the menu refuses every action the action itself refuses, with the
// same error. The response attack of the decision is the question, so the plan
// is built without one.
func Menu(board *battle.BattleState, decision battle.Decision, defenderID string) (Options, error) {
	decision.ResponseAttack = nil
	plan, err := Prepare(board, decision)
	if err != nil {
		return Options{}, err
	}
	if plan.kind != battle.ActionAttack {
		return Options{}, fmt.Errorf("%w: an action of the kind %q asks unit %q nothing",
			battle.ErrIllegalAction, plan.kind, defenderID)
	}
	defender, err := LivingUnit(board, defenderID)
	if err != nil {
		return Options{}, err
	}
	attacker, weapon := plan.actor, plan.weapon
	origin := geometry.FootprintAt(attacker, plan.anchor)
	distance := geometry.Distance(defender.Footprint(), origin)
	if !weapon.Reaches(distance) {
		return Options{}, fmt.Errorf("%w: the weapon %q of unit %q does not reach unit %q from %v",
			battle.ErrIllegalAction, weapon.Name, attacker.ID, defenderID, origin.Anchor)
	}
	out := Options{
		Defender:        SideOptions{Unit: defender},
		Attacker:        SideOptions{Unit: attacker},
		ResponseAttacks: []ResponseAttackOption{},
	}

	out.ResponseAttacks = append(out.ResponseAttacks,
		stanceOption(attacker, defender, weapon, battle.StanceDodge, ""),
		stanceOption(attacker, defender, weapon, battle.StanceDefend, ""))
	for index := range defender.Mech.Weapons {
		counter := &defender.Mech.Weapons[index]
		if !fires(defender, counter, distance) {
			continue
		}
		option := stanceOption(attacker, defender, weapon, battle.StanceCounter, counter.Name)
		reply := forecastOf(defender, attacker, counter, formula.NoDefenseMultiplier, false)
		option.Counter = &reply
		out.ResponseAttacks = append(out.ResponseAttacks, option)
	}
	out.ResponseAttacks = append(out.ResponseAttacks,
		stanceOption(attacker, defender, weapon, battle.StanceNone, ""))

	out.Defender.SupportDefenders = defendOptions(attacker, weapon,
		supportDefenders(board, defender, defender.Footprint()))
	out.Defender.SupportAttackers = attackOptions(attacker,
		supportAttackers(board, defender, defender.Footprint(), origin))
	// Which weapon counters is the pick of the defender, so the entry of a
	// unit that covers the attacker carries no forecast.
	out.Attacker.SupportDefenders = defendOptions(defender, nil,
		supportDefenders(board, attacker, origin))
	out.Attacker.SupportAttackers = attackOptions(defender,
		supportAttackers(board, attacker, origin, defender.Footprint()))
	return out, nil
}

func stanceOption(attacker, defender *battle.Unit, weapon *battle.Weapon, stance battle.Stance,
	counter string) ResponseAttackOption {
	return ResponseAttackOption{
		Stance: stance,
		Weapon: counter,
		Incoming: forecastOf(attacker, defender, weapon,
			defenseMultiplier(stance, defender), stance == battle.StanceDodge),
	}
}

func defendOptions(shooter *battle.Unit, weapon *battle.Weapon, units []*battle.Unit) []SupportDefendOption {
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
func attackOptions(foe *battle.Unit, joining []supportAttacker) []SupportAttackOption {
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
