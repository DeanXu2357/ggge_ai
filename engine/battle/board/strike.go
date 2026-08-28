package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
)

func attackerSide(attacker *Unit, weapon Weapon) formula.Side {
	return formula.Side{
		PilotAttack:   attacker.Pilot.attackFor(weapon),
		PilotDefense:  attacker.Pilot.Defense,
		PilotReaction: attacker.Pilot.Reaction,
		MechAttack:    attacker.Mech.Attack,
		MechDefense:   attacker.Mech.Defense,
		Mobility:      attacker.Mech.Mobility,
	}
}

// No formula reads the pilot attack of the defender, and the weapon of the
// strike belongs to the attacker, so the defender side carries no attack value.
func defenderSide(defender *Unit) formula.Side {
	return formula.Side{
		PilotDefense:  defender.Pilot.Defense,
		PilotReaction: defender.Pilot.Reaction,
		MechAttack:    defender.Mech.Attack,
		MechDefense:   defender.Mech.Defense,
		Mobility:      defender.Mech.Mobility,
	}
}

// The terrain correction is NoTerrainCorrection for every weapon. The
// correction is the effect of a weapon ability that reads the terrain of the
// cell of the target, and the engine models no ability yet. Issue #80 gives
// the weapon its ability list, and this call then reads the board.
func strikeDamage(attacker, defender *Unit, weapon *Weapon, defense float64) int {
	return formula.StrikeDamage(weapon.Power, attackerSide(attacker, *weapon),
		defenderSide(defender), formula.NoTerrainCorrection, debuffBonus(defender), 0,
		defense)
}

func debuffBonus(defender *Unit) float64 {
	var sum float64
	for _, debuff := range defender.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

func strikeHitProbability(attacker, defender *Unit, weapon *Weapon, dodging bool) float64 {
	return formula.StrikeHitProbability(weapon.Accuracy, attackerSide(attacker, *weapon),
		defenderSide(defender), dodging)
}

// The response attack menu offers no shield stance, so a defender that
// carries a shield defends with the shield here, in the damage (issue #63).
func defenseMultiplier(stance stance, defender *Unit) float64 {
	return formula.DefenseMultiplier(stance == stanceDefend, defender.HasShield)
}

func (b *Board) counterWeapon(defender *Unit, name string, attacker footprint) *Weapon {
	distance := spanDistance(defender.Footprint, attacker)
	for index := range defender.Mech.Weapons {
		weapon := &defender.Mech.Weapons[index]
		if name != "" && weapon.Name != name {
			continue
		}
		if counterFits(defender, weapon, distance) {
			return weapon
		}
	}
	return nil
}

func counterFits(defender *Unit, weapon *Weapon, distance int) bool {
	return !weapon.MapWeapon && weapon.CanCounter && defender.hasENFor(*weapon) &&
		weapon.Range.holds(distance)
}
