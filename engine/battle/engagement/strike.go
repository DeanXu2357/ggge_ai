package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
)

func attackFor(pilot *battle.Pilot, weapon battle.Weapon) float64 {
	categories := weapon.Categories
	if len(categories) == 0 {
		categories = battle.WeaponCategories[:]
	}
	highest := attackOf(pilot, categories[0])
	for _, category := range categories[1:] {
		if value := attackOf(pilot, category); value > highest {
			highest = value
		}
	}
	return highest
}

func attackOf(pilot *battle.Pilot, category battle.WeaponCategory) float64 {
	switch category {
	case battle.WeaponCategoryRanged:
		return pilot.Ranged
	case battle.WeaponCategoryMelee:
		return pilot.Melee
	case battle.WeaponCategoryAwaken:
		return pilot.Awaken
	}
	return 0
}

func attackerSide(attacker *battle.Unit, weapon battle.Weapon) formula.Side {
	return formula.Side{
		PilotAttack:   attackFor(&attacker.Pilot, weapon),
		PilotDefense:  attacker.Pilot.Defense,
		PilotReaction: attacker.Pilot.Reaction,
		MechAttack:    attacker.Mech.Attack,
		MechDefense:   attacker.Mech.Defense,
		Mobility:      attacker.Mech.Mobility,
	}
}

// No formula reads the pilot attack of the defender, and the weapon of the
// strike belongs to the attacker, so the defender side carries no attack value.
func defenderSide(defender *battle.Unit) formula.Side {
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
// cell of the target, and the engine models no ability yet.
func strikeDamage(attacker, defender *battle.Unit, weapon *battle.Weapon, defense float64) int {
	return formula.StrikeDamage(weapon.Power, attackerSide(attacker, *weapon),
		defenderSide(defender), formula.NoTerrainCorrection, debuffBonus(defender), 0,
		defense)
}

func debuffBonus(defender *battle.Unit) float64 {
	var sum float64
	for _, debuff := range defender.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

func strikeHitProbability(attacker, defender *battle.Unit, weapon *battle.Weapon, dodging bool) float64 {
	return formula.StrikeHitProbability(weapon.Accuracy, attackerSide(attacker, *weapon),
		defenderSide(defender), dodging)
}

// The response attack menu offers no shield stance, so a defender that
// carries a shield defends with the shield here, in the damage (issue #63).
func defenseMultiplier(stance Stance, defender *battle.Unit) float64 {
	return formula.DefenseMultiplier(stance == StanceDefend, defender.HasShield)
}

func counterWeapon(defender *battle.Unit, name string, attacker battle.Footprint) *battle.Weapon {
	distance := geometry.Distance(defender.Footprint(), attacker)
	for index := range defender.Mech.Weapons {
		weapon := &defender.Mech.Weapons[index]
		if name != "" && weapon.Name != name {
			continue
		}
		if fires(defender, weapon, distance) {
			return weapon
		}
	}
	return nil
}
