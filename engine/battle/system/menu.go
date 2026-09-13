package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// Menu answers the question 'response_attacks' from the plan that 'act' would
// run, so the menu refuses every action the action itself refuses, with the
// same error. The response attack of the decision is the question, so the plan
// is built without one.
func Menu(board state.Battle, decision battle.Decision, defenderID int) (Options, error) {
	decision.ResponseAttack = nil
	made, err := prepare(board, decision)
	if err != nil {
		return Options{}, err
	}
	if made.kind != battle.ActionAttack {
		return Options{}, fmt.Errorf("%w: an action of the kind %q asks unit %d nothing",
			battle.ErrIllegalAction, made.kind, defenderID)
	}
	defender, err := LivingUnit(board, defenderID)
	if err != nil {
		return Options{}, err
	}
	attacker := unitOf(board, made.actorID)
	weapon := weaponOf(attacker, *made.weaponID)
	origin := geometry.FootprintAt(attacker, made.anchor)
	distance := geometry.Distance(defender.Footprint(), origin)
	if !weapon.Reaches(distance) {
		return Options{}, fmt.Errorf("%w: the weapon %q of unit %d does not reach unit %d from %v",
			battle.ErrIllegalAction, weapon.Name, made.actorID, defenderID, origin.Anchor)
	}
	out := Options{
		Defender:        SideOptions{UnitID: defenderID},
		Attacker:        SideOptions{UnitID: made.actorID},
		ResponseAttacks: []ResponseAttackOption{},
	}

	out.ResponseAttacks = append(out.ResponseAttacks,
		stanceOption(attacker, defender, weapon, battle.StanceDodge, nil),
		stanceOption(attacker, defender, weapon, battle.StanceDefend, nil))
	for index := range defender.Mech.Weapons {
		counter := &defender.Mech.Weapons[index]
		if !fires(defender, counter, distance) {
			continue
		}
		counterID := index
		option := stanceOption(attacker, defender, weapon, battle.StanceCounter, &counterID)
		reply := forecastOf(defender, attacker, counter, formula.NoDefenseMultiplier, false)
		option.Counter = &reply
		out.ResponseAttacks = append(out.ResponseAttacks, option)
	}
	out.ResponseAttacks = append(out.ResponseAttacks,
		stanceOption(attacker, defender, weapon, battle.StanceNone, nil))

	out.Defender.SupportDefenders = defendOptions(board, attacker, weapon,
		supportDefenders(board, defenderID, defender.Footprint()))
	out.Defender.SupportAttackers = attackOptions(board, attacker,
		supportAttackers(board, defenderID, defender.Footprint(), origin))
	// Which weapon counters is the choice of the defender, so the entry of a
	// unit that covers the attacker carries no forecast.
	out.Attacker.SupportDefenders = defendOptions(board, defender, nil,
		supportDefenders(board, made.actorID, origin))
	out.Attacker.SupportAttackers = attackOptions(board, defender,
		supportAttackers(board, made.actorID, origin, defender.Footprint()))
	return out, nil
}

func stanceOption(attacker, defender state.Unit, weapon *def.Weapon, stance battle.Stance,
	counterID *int) ResponseAttackOption {
	return ResponseAttackOption{
		Stance:   stance,
		WeaponID: counterID,
		Incoming: forecastOf(attacker, defender, weapon,
			defenseMultiplier(stance, defender), stance == battle.StanceDodge),
	}
}

func defendOptions(board state.Battle, shooter state.Unit, weapon *def.Weapon,
	ids []int) []SupportDefendOption {
	out := make([]SupportDefendOption, 0, len(ids))
	for _, id := range ids {
		option := SupportDefendOption{UnitID: id}
		if weapon != nil {
			option.Incoming = supportDefenderForecast(shooter, unitOf(board, id), weapon)
		}
		out = append(out, option)
	}
	return out
}

// The foe settles its stance after this answer, so the forecast of a support
// attack reads no defense.
func attackOptions(board state.Battle, foe state.Unit,
	joining []supportAttacker) []SupportAttackOption {
	out := make([]SupportAttackOption, 0, len(joining))
	for _, one := range joining {
		shooter := unitOf(board, one.UnitID)
		out = append(out, SupportAttackOption{
			UnitID:   one.UnitID,
			WeaponID: one.WeaponID,
			Strike: forecastOf(shooter, foe, weaponOf(shooter, one.WeaponID),
				formula.NoDefenseMultiplier, false),
		})
	}
	return out
}
