package system

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

func (x *exchange) forecastOf(shooter, struck unit, weapon *def.Weapon, multiplier float64,
	dodging bool) Forecast {
	a, d := x.attackContext(shooter, struck, weapon), x.defendContext(shooter, struck, weapon)
	rate := hitRateOf(a, d, dodging)
	damage := damageOf(a, d, multiplier)
	kill := damage >= struck.Value.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func (x *exchange) supportDefenderForecast(attacker, supportDefender unit, weapon *def.Weapon) Forecast {
	damage := x.strikeDamage(attacker, supportDefender, weapon,
		defenseMultiplier(battle.StanceDefend, supportDefender))
	kill := damage >= supportDefender.Value.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
