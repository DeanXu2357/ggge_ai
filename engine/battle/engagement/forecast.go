package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func forecastOf(shooter, struck state.Unit, weapon *def.Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := strikeHitProbability(shooter, struck, weapon, dodging)
	damage := strikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.Value.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func supportDefenderForecast(attacker, supportDefender state.Unit, weapon *def.Weapon) Forecast {
	damage := strikeDamage(attacker, supportDefender, weapon,
		defenseMultiplier(battle.StanceDefend, supportDefender))
	kill := damage >= supportDefender.Value.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
