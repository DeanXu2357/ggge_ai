package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func (b *Board) forecastOf(shooter, struck *state.Unit, weapon *def.Weapon, multiplier float64,
	dodging bool) forecast {
	rate := strikeHitProbability(shooter, struck, weapon, dodging)
	damage := strikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.HP
	return forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func (b *Board) supportDefenderForecast(attacker, supportDefender *state.Unit, weapon *def.Weapon) forecast {
	damage := strikeDamage(attacker, supportDefender, weapon,
		defenseMultiplier(stanceDefend, supportDefender))
	kill := damage >= supportDefender.HP
	return forecast{Damage: &damage, Kill: &kill}
}
