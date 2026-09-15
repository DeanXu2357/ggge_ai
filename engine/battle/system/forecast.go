package system

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

func forecastOf(shooter, struck unit, weapon *def.Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := strikeHitProbability(shooter, struck, weapon, dodging)
	damage := strikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.Value.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func supportDefenderForecast(attacker, supportDefender unit, weapon *def.Weapon) Forecast {
	damage := strikeDamage(attacker, supportDefender, weapon,
		defenseMultiplier(battle.StanceDefend, supportDefender))
	kill := damage >= supportDefender.Value.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
