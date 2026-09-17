package lines

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// Unknown is a line of a kind the engine does not model. No hook reads it,
// and it goes back on the wire as it came (issue #80).
type Unknown struct{ Wire battle.Ability }

func (l Unknown) Clone() ability.Line { return l }

// FromContract picks the line of a wire ability by its kind and by the
// condition fields it carries. A known kind with a set of conditions the
// engine does not model is refused, so that no line is carried and
// silently read by nothing.
func FromContract(a battle.Ability) (ability.Line, error) {
	line := pick(a)
	if line == nil {
		return nil, fmt.Errorf("%w: the ability %q carries conditions the engine does not model: %+v",
			battle.ErrOutsideContract, a.Kind, a)
	}
	return line, nil
}

func pick(a battle.Ability) ability.Line {
	conditions := conditionsOf(a)
	switch a.Kind {
	case battle.AbilityAccuracyPercent:
		if conditions == none {
			return AccuracyPercent{Percent: a.Percent}
		}
	case battle.AbilityEvasionPercent:
		if conditions == none {
			return EvasionPercent{Percent: a.Percent}
		}
	case battle.AbilityMechAttackPercent:
		switch conditions {
		case none:
			return MechAttackPercent{Percent: a.Percent}
		case enemyTag:
			return MechAttackPercentAgainstTag{EnemyTag: a.EnemyTag, Percent: a.Percent}
		case hpRateLte:
			return MechAttackPercentAtHPRateAtMost{Threshold: a.HPRateLte, Percent: a.Percent}
		case mechType | strikeRole:
			if *a.StrikeRole == battle.StrikeRoleSupportAttack {
				return MechAttackPercentOnSupportWithMechType{MechType: a.MechType, Percent: a.Percent}
			}
		}
	case battle.AbilityMechDefensePercent:
		switch conditions {
		case none:
			return MechDefensePercent{Percent: a.Percent}
		case enemyTag:
			return MechDefensePercentAgainstTag{EnemyTag: a.EnemyTag, Percent: a.Percent}
		case hpRateLte:
			return MechDefensePercentAtHPRateAtMost{Threshold: a.HPRateLte, Percent: a.Percent}
		case hpRateGte:
			return MechDefensePercentAtHPRateAtLeast{Threshold: a.HPRateGte, Percent: a.Percent}
		case strikeRole:
			if *a.StrikeRole == battle.StrikeRoleSupportDefense {
				return MechDefensePercentOnSupportDefense{Percent: a.Percent}
			}
		case mechType | strikeRole:
			if *a.StrikeRole == battle.StrikeRoleSupportDefense {
				return MechDefensePercentOnSupportDefenseWithMechType{MechType: a.MechType, Percent: a.Percent}
			}
		}
	case battle.AbilityMechMobilityPercent:
		if conditions == none {
			return MechMobilityPercent{Percent: a.Percent}
		}
	case battle.AbilityPilotRangedPercent:
		if conditions == none {
			return PilotRangedPercent{Percent: a.Percent}
		}
	case battle.AbilityPilotMeleePercent:
		if conditions == none {
			return PilotMeleePercent{Percent: a.Percent}
		}
	case battle.AbilityPilotAwakenPercent:
		if conditions == none {
			return PilotAwakenPercent{Percent: a.Percent}
		}
	case battle.AbilityPilotDefensePercent:
		if conditions == none {
			return PilotDefensePercent{Percent: a.Percent}
		}
	case battle.AbilityPilotReactionPercent:
		if conditions == none {
			return PilotReactionPercent{Percent: a.Percent}
		}
	case battle.AbilityDamageDealtPercent:
		switch conditions {
		case none:
			return DamageDealtPercent{Percent: a.Percent}
		case mechTag:
			return DamageDealtPercentOnMechTag{MechTag: a.MechTag, Percent: a.Percent}
		case enemyTag:
			return DamageDealtPercentAgainstTag{EnemyTag: a.EnemyTag, Percent: a.Percent}
		}
	case battle.AbilityDamageTakenPercent:
		switch conditions {
		case mechTag:
			return DamageTakenPercentOnMechTag{MechTag: a.MechTag, Percent: a.Percent}
		case enemyTag:
			return DamageTakenPercentAgainstTag{EnemyTag: a.EnemyTag, Percent: a.Percent}
		case weaponAttribute:
			return DamageTakenPercentAgainstWeaponAttribute{Attribute: *a.WeaponAttribute, Percent: a.Percent}
		case weaponAttribute | weaponCategory:
			return DamageTakenPercentAgainstWeaponAttributeAndCategory{
				Attribute: *a.WeaponAttribute, Category: *a.WeaponCategory, Percent: a.Percent}
		}
	case battle.AbilityWeaponENCostPercent:
		if conditions == mechType|strikeRole && *a.StrikeRole == battle.StrikeRoleSupportAttack {
			return WeaponENCostPercentOnSupportWithMechType{MechType: a.MechType, Percent: a.Percent}
		}
	default:
		return Unknown{Wire: a}
	}
	return nil
}

type conditionSet int

const (
	none     conditionSet = 0
	enemyTag conditionSet = 1 << iota
	mechTag
	hpRateLte
	hpRateGte
	mechType
	strikeRole
	weaponAttribute
	weaponCategory
)

func conditionsOf(a battle.Ability) conditionSet {
	var out conditionSet
	for _, one := range []struct {
		set  bool
		flag conditionSet
	}{
		{a.EnemyTag != 0, enemyTag}, {a.MechTag != 0, mechTag},
		{a.HPRateLte != 0, hpRateLte}, {a.HPRateGte != 0, hpRateGte},
		{a.MechType != 0, mechType}, {a.StrikeRole != nil, strikeRole},
		{a.WeaponAttribute != nil, weaponAttribute}, {a.WeaponCategory != nil, weaponCategory},
	} {
		if one.set {
			out |= one.flag
		}
	}
	return out
}

// ToContract writes a line back in its wire form.
func ToContract(line ability.Line) battle.Ability {
	switch l := line.(type) {
	case Unknown:
		return l.Wire
	case AccuracyPercent:
		return battle.Ability{Kind: battle.AbilityAccuracyPercent, Percent: l.Percent}
	case EvasionPercent:
		return battle.Ability{Kind: battle.AbilityEvasionPercent, Percent: l.Percent}
	case MechAttackPercent:
		return battle.Ability{Kind: battle.AbilityMechAttackPercent, Percent: l.Percent}
	case MechAttackPercentAgainstTag:
		return battle.Ability{Kind: battle.AbilityMechAttackPercent, Percent: l.Percent, EnemyTag: l.EnemyTag}
	case MechAttackPercentAtHPRateAtMost:
		return battle.Ability{Kind: battle.AbilityMechAttackPercent, Percent: l.Percent, HPRateLte: l.Threshold}
	case MechAttackPercentOnSupportWithMechType:
		return battle.Ability{Kind: battle.AbilityMechAttackPercent, Percent: l.Percent,
			MechType: l.MechType, StrikeRole: ptr(battle.StrikeRoleSupportAttack)}
	case MechDefensePercent:
		return battle.Ability{Kind: battle.AbilityMechDefensePercent, Percent: l.Percent}
	case MechDefensePercentAgainstTag:
		return battle.Ability{Kind: battle.AbilityMechDefensePercent, Percent: l.Percent, EnemyTag: l.EnemyTag}
	case MechDefensePercentAtHPRateAtMost:
		return battle.Ability{Kind: battle.AbilityMechDefensePercent, Percent: l.Percent, HPRateLte: l.Threshold}
	case MechDefensePercentAtHPRateAtLeast:
		return battle.Ability{Kind: battle.AbilityMechDefensePercent, Percent: l.Percent, HPRateGte: l.Threshold}
	case MechDefensePercentOnSupportDefense:
		return battle.Ability{Kind: battle.AbilityMechDefensePercent, Percent: l.Percent,
			StrikeRole: ptr(battle.StrikeRoleSupportDefense)}
	case MechDefensePercentOnSupportDefenseWithMechType:
		return battle.Ability{Kind: battle.AbilityMechDefensePercent, Percent: l.Percent,
			MechType: l.MechType, StrikeRole: ptr(battle.StrikeRoleSupportDefense)}
	case MechMobilityPercent:
		return battle.Ability{Kind: battle.AbilityMechMobilityPercent, Percent: l.Percent}
	case PilotRangedPercent:
		return battle.Ability{Kind: battle.AbilityPilotRangedPercent, Percent: l.Percent}
	case PilotMeleePercent:
		return battle.Ability{Kind: battle.AbilityPilotMeleePercent, Percent: l.Percent}
	case PilotAwakenPercent:
		return battle.Ability{Kind: battle.AbilityPilotAwakenPercent, Percent: l.Percent}
	case PilotDefensePercent:
		return battle.Ability{Kind: battle.AbilityPilotDefensePercent, Percent: l.Percent}
	case PilotReactionPercent:
		return battle.Ability{Kind: battle.AbilityPilotReactionPercent, Percent: l.Percent}
	case DamageDealtPercent:
		return battle.Ability{Kind: battle.AbilityDamageDealtPercent, Percent: l.Percent}
	case DamageDealtPercentOnMechTag:
		return battle.Ability{Kind: battle.AbilityDamageDealtPercent, Percent: l.Percent, MechTag: l.MechTag}
	case DamageDealtPercentAgainstTag:
		return battle.Ability{Kind: battle.AbilityDamageDealtPercent, Percent: l.Percent, EnemyTag: l.EnemyTag}
	case DamageTakenPercentOnMechTag:
		return battle.Ability{Kind: battle.AbilityDamageTakenPercent, Percent: l.Percent, MechTag: l.MechTag}
	case DamageTakenPercentAgainstTag:
		return battle.Ability{Kind: battle.AbilityDamageTakenPercent, Percent: l.Percent, EnemyTag: l.EnemyTag}
	case DamageTakenPercentAgainstWeaponAttribute:
		return battle.Ability{Kind: battle.AbilityDamageTakenPercent, Percent: l.Percent, WeaponAttribute: ptr(l.Attribute)}
	case DamageTakenPercentAgainstWeaponAttributeAndCategory:
		return battle.Ability{Kind: battle.AbilityDamageTakenPercent, Percent: l.Percent,
			WeaponAttribute: ptr(l.Attribute), WeaponCategory: ptr(l.Category)}
	case WeaponENCostPercentOnSupportWithMechType:
		return battle.Ability{Kind: battle.AbilityWeaponENCostPercent, Percent: l.Percent,
			MechType: l.MechType, StrikeRole: ptr(battle.StrikeRoleSupportAttack)}
	}
	panic(fmt.Sprintf("the line %T has no wire form", line))
}

func ptr[T any](value T) *T { return &value }
