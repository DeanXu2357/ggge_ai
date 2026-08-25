package battle

type Forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

func (b *Board) forecastOf(shooter, struck *Unit, weapon *Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := StrikeHitProbability(shooter, struck, weapon, dodging, b.Rules)
	damage := b.StrikeDamage(shooter, struck, weapon, multiplier)
	kill := damage >= struck.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The stance of the defender settles the hit roll of the strike, so an
// interception entry carries the damage alone and no hit rate.
func (b *Board) interceptionForecast(attacker, interceptor *Unit, weapon *Weapon) Forecast {
	damage := b.StrikeDamage(attacker, interceptor, weapon,
		b.Rules.InterceptionMultiplier(interceptor))
	kill := damage >= interceptor.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
