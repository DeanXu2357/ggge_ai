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

// cast is who is who in one exchange, settled one time when the exchange
// is scheduled: the actor, its target, and every other unit supports.
type cast struct {
	actorID, targetID int
}

func (c cast) part(unitID int) ability.Part {
	switch unitID {
	case c.actorID:
		return ability.PartAttacker
	case c.targetID:
		return ability.PartTarget
	}
	return ability.PartSupport
}

func attackerSide(a ability.AttackContext) formula.Side {
	pilot := *a.Attacker.Pilot
	pilot.Ranged = scaled(pilot.Ranged, a.PilotRangedPercent)
	pilot.Melee = scaled(pilot.Melee, a.PilotMeleePercent)
	pilot.Awaken = scaled(pilot.Awaken, a.PilotAwakenPercent)
	return formula.Side{
		PilotAttack:   attackFor(&pilot, *a.Weapon),
		PilotDefense:  a.Attacker.Pilot.Defense,
		PilotReaction: a.Attacker.Pilot.Reaction,
		MechAttack:    scaled(a.Attacker.Mech.Attack, a.MechAttackPercent),
		MechDefense:   a.Attacker.Mech.Defense,
		Mobility:      scaled(a.Attacker.Mech.Mobility, a.MechMobilityPercent),
	}
}

// No formula reads the pilot attack of the defender, and the weapon of the
// strike belongs to the attacker, so the defender side carries no attack value.
func defenderSide(d ability.DefendContext) formula.Side {
	return formula.Side{
		PilotDefense:  scaled(d.Defender.Pilot.Defense, d.PilotDefensePercent),
		PilotReaction: scaled(d.Defender.Pilot.Reaction, d.PilotReactionPercent),
		MechAttack:    d.Defender.Mech.Attack,
		MechDefense:   scaled(d.Defender.Mech.Defense, d.MechDefensePercent),
		Mobility:      scaled(d.Defender.Mech.Mobility, d.MechMobilityPercent),
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
func damageOf(a ability.AttackContext, d ability.DefendContext, defense float64) int {
	return formula.StrikeDamage(a.Weapon.Power, attackerSide(a), defenderSide(d),
		formula.NoTerrainCorrection, damageScaleSum(a, d), 0, defense)
}

// The sum of ⑨: the damage dealt of the attacker, the damage taken of the
// defender and the debuffs of the defender add, and the formula multiplies
// one time (docs/reference/combat-formulas.md, 增減傷合算後才乘).
func damageScaleSum(a ability.AttackContext, d ability.DefendContext) float64 {
	sum := a.DamageDealtPercent/100 + d.DamageTakenPercent/100
	for _, debuff := range d.Defender.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

func hitRateOf(a ability.AttackContext, d ability.DefendContext, dodging bool) float64 {
	return formula.StrikeHitProbability(a.Weapon.Accuracy, attackerSide(a), defenderSide(d),
		a.AccuracyPercent-d.EvasionPercent, dodging)
}

// strikeDamage and strikeHitProbability are the two computations from the
// units, for a reader that holds no context of its own.
func (x *exchange) strikeDamage(attacker, defender unit, weapon *def.Weapon, defense float64) int {
	return damageOf(x.attackContext(attacker, defender, weapon), x.defendContext(attacker, defender, weapon), defense)
}

func (x *exchange) strikeHitProbability(attacker, defender unit, weapon *def.Weapon, dodging bool) float64 {
	return hitRateOf(x.attackContext(attacker, defender, weapon), x.defendContext(attacker, defender, weapon), dodging)
}

// The response attack menu offers no shield stance, so a defender that
// carries a shield defends with the shield here, in the damage (issue #63).
func defenseMultiplier(stance battle.Stance, defender unit) float64 {
	return formula.DefenseMultiplier(stance == battle.StanceDefend, defender.HasShield)
}
