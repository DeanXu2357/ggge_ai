package board

import "github.com/DeanXu2357/ggge_ai/engine/battle"

func (b *Board) forecastOf(shooter, struck *battle.Unit, weapon *battle.Weapon, multiplier float64,
	dodging bool) battle.Forecast {
	rate := StrikeHitProbability(shooter, struck, weapon, dodging)
	damage := StrikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.HP
	return battle.Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func (b *Board) supportDefenderForecast(attacker, supportDefender *battle.Unit, weapon *battle.Weapon) battle.Forecast {
	damage := StrikeDamage(attacker, supportDefender, weapon,
		StanceMultiplier(battle.StanceDefend, supportDefender))
	kill := damage >= supportDefender.HP
	return battle.Forecast{Damage: &damage, Kill: &kill}
}
