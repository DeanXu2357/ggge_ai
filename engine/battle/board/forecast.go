package board

func (b *Board) forecastOf(shooter, struck *Unit, weapon *Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := StrikeHitProbability(shooter, struck, weapon, dodging)
	damage := StrikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so a support
// defense entry carries the damage alone and no hit rate.
func (b *Board) supportDefenderForecast(attacker, supportDefender *Unit, weapon *Weapon) Forecast {
	damage := StrikeDamage(attacker, supportDefender, weapon,
		StanceMultiplier(StanceDefend, supportDefender))
	kill := damage >= supportDefender.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
