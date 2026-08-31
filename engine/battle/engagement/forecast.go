package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func forecastOf(shooter, struck *battle.Unit, weapon *battle.Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := strikeHitProbability(shooter, struck, weapon, dodging)
	damage := strikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func supportDefenderForecast(attacker, supportDefender *battle.Unit, weapon *battle.Weapon) Forecast {
	damage := strikeDamage(attacker, supportDefender, weapon,
		defenseMultiplier(battle.StanceDefend, supportDefender))
	kill := damage >= supportDefender.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
