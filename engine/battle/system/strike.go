package system

import (
	"math"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
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

func attackerSide(attacker, defender unit, weapon *def.Weapon) formula.Side {
	a := ability.AttackContext{Attacker: attacker.hookView(), Defender: defender.hookView(), Weapon: weapon}
	attacker.Value.Hooks.Attack(&a)
	pilot := *attacker.Pilot
	pilot.Ranged = scaled(pilot.Ranged, a.PilotRangedPercent)
	pilot.Melee = scaled(pilot.Melee, a.PilotMeleePercent)
	pilot.Awaken = scaled(pilot.Awaken, a.PilotAwakenPercent)
	return formula.Side{
		PilotAttack:   attackFor(&pilot, *weapon),
		PilotDefense:  attacker.Pilot.Defense,
		PilotReaction: attacker.Pilot.Reaction,
		MechAttack:    scaled(attacker.Mech.Attack, a.MechAttackPercent),
		MechDefense:   attacker.Mech.Defense,
		Mobility:      scaled(attacker.Mech.Mobility, a.MechMobilityPercent),
	}
}

// No formula reads the pilot attack of the defender, and the weapon of the
// strike belongs to the attacker, so the defender side carries no attack value.
func defenderSide(defender, attacker unit, weapon *def.Weapon) formula.Side {
	d := ability.DefendContext{Attacker: attacker.hookView(), Defender: defender.hookView(), Weapon: weapon}
	defender.Value.Hooks.Defend(&d)
	return formula.Side{
		PilotDefense:  scaled(defender.Pilot.Defense, d.PilotDefensePercent),
		PilotReaction: scaled(defender.Pilot.Reaction, d.PilotReactionPercent),
		MechAttack:    defender.Mech.Attack,
		MechDefense:   scaled(defender.Mech.Defense, d.MechDefensePercent),
		Mobility:      scaled(defender.Mech.Mobility, d.MechMobilityPercent),
	}
}

// The percents of every source on one stat add, the sum multiplies the base
// one time, and the result is floored (measured on 2026-08-29). A stat that
// no line touches keeps its base as it came, fraction included.
func scaled(base, percent float64) float64 {
	if percent == 0 {
		return base
	}
	return math.Floor(base * (100 + percent) / 100)
}

// The terrain correction is NoTerrainCorrection for every weapon. The
// correction is the effect of a weapon ability that reads the terrain of the
// cell of the target, and the engine models no ability yet.
func strikeDamage(attacker, defender unit, weapon *def.Weapon, defense float64) int {
	return formula.StrikeDamage(weapon.Power, attackerSide(attacker, defender, weapon),
		defenderSide(defender, attacker, weapon), formula.NoTerrainCorrection,
		debuffBonus(defender), 0, defense)
}

func debuffBonus(defender unit) float64 {
	var sum float64
	for _, debuff := range defender.Value.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

func strikeHitProbability(attacker, defender unit, weapon *def.Weapon, dodging bool) float64 {
	return formula.StrikeHitProbability(weapon.Accuracy, attackerSide(attacker, defender, weapon),
		defenderSide(defender, attacker, weapon), dodging)
}

// The response attack menu offers no shield stance, so a defender that
// carries a shield defends with the shield here, in the damage (issue #63).
func defenseMultiplier(stance battle.Stance, defender unit) float64 {
	return formula.DefenseMultiplier(stance == battle.StanceDefend, defender.HasShield)
}
