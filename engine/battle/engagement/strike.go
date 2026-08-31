package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func attackFor(pilot *def.Pilot, weapon def.Weapon) float64 {
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

func attackOf(pilot *def.Pilot, category battle.WeaponCategory) float64 {
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

func attackerSide(attacker *state.Unit, weapon def.Weapon) formula.Side {
	return formula.Side{
		PilotAttack:   attackFor(attacker.Pilot, weapon),
		PilotDefense:  attacker.Pilot.Defense,
		PilotReaction: attacker.Pilot.Reaction,
		MechAttack:    attacker.Mech.Attack,
		MechDefense:   attacker.Mech.Defense,
		Mobility:      attacker.Mech.Mobility,
	}
}

// No formula reads the pilot attack of the defender, and the weapon of the
// strike belongs to the attacker, so the defender side carries no attack value.
func defenderSide(defender *state.Unit) formula.Side {
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
func strikeDamage(attacker, defender *state.Unit, weapon *def.Weapon, defense float64) int {
	return formula.StrikeDamage(weapon.Power, attackerSide(attacker, *weapon),
		defenderSide(defender), formula.NoTerrainCorrection, debuffBonus(defender), 0,
		defense)
}

func debuffBonus(defender *state.Unit) float64 {
	var sum float64
	for _, debuff := range defender.Value.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

func strikeHitProbability(attacker, defender *state.Unit, weapon *def.Weapon, dodging bool) float64 {
	return formula.StrikeHitProbability(weapon.Accuracy, attackerSide(attacker, *weapon),
		defenderSide(defender), dodging)
}

// The response attack menu offers no shield stance, so a defender that
// carries a shield defends with the shield here, in the damage (issue #63).
func defenseMultiplier(stance battle.Stance, defender *state.Unit) float64 {
	return formula.DefenseMultiplier(stance == battle.StanceDefend, defender.HasShield)
}

func counterWeapon(defender *state.Unit, name string, attacker battle.Footprint) *def.Weapon {
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
