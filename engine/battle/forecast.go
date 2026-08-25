package battle

// Forecast is what one shot does to one unit, before any die settles. The
// engine reports it for each entry of an engagement, and the client shows it
// (docs/spec/battle-engine-protocol.md).
//
// Damage is the conservative lower bound: no critical hit and no bonus beside
// the debuffs the target already carries. Kill reads that bound alone and no
// hit roll, so a Kill of a dodge entry says "the strike destroys this unit when
// it lands".
type Forecast struct {
	HitRate *float64
	Damage  *int
	Kill    *bool
}

// forecastOf computes one shot without a change of the board: it reads the
// state of the two units and gives the numbers back.
func (b *Board) forecastOf(shooter, struck *Unit, weapon *Weapon, multiplier float64,
	dodging bool) Forecast {
	rate := StrikeHitProbability(shooter, struck, weapon, dodging, b.Rules)
	damage := StrikeDamage(shooter, struck, weapon, multiplier, b.Rules)
	kill := damage >= struck.HP
	return Forecast{HitRate: &rate, Damage: &damage, Kill: &kill}
}

// The interceptor takes the strike in place of the defender, and the stance of
// the defender settles the hit roll of that strike. The entry of an interceptor
// therefore carries the damage it takes and no hit rate: the rate stands beside
// the stance the client picks.
func (b *Board) interceptionForecast(attacker, interceptor *Unit, weapon *Weapon) Forecast {
	damage := StrikeDamage(attacker, interceptor, weapon, b.Rules.InterceptionMultiplier(interceptor),
		b.Rules)
	kill := damage >= interceptor.HP
	return Forecast{Damage: &damage, Kill: &kill}
}
