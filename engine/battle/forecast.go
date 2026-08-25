package battle

type Forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

func (b *Board) forecastOf(shooter, struck *Unit, weapon *Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := StrikeHitProbability(shooter, struck, weapon, dodging, b.Rules)
	damage := StrikeDamage(shooter, struck, weapon, multiplier, b.Rules)
	kill := damage >= struck.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so an
// interception entry carries the damage alone and no hit rate.
func (b *Board) interceptionForecast(attacker, interceptor *Unit, weapon *Weapon) Forecast {
	damage := StrikeDamage(attacker, interceptor, weapon, b.Rules.InterceptionMultiplier(interceptor),
		b.Rules)
	kill := damage >= interceptor.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
