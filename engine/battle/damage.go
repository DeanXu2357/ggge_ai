package battle

import "math"

// The damage rules of docs/reference/combat-formulas.md. The unexported
// functions are the corrections 1 to 4, 6 and 7 of that document, and the
// exported ones are the formulas 5 and 8 to 11, plus the composition of the
// formulas 8 to 10. The constants are the multipliers the same document lists.
const (
	NoDefenseMultiplier = 1.0
	NoTerrainCorrection = 1.0
	DefendMultiplier    = 0.8
	ShieldMultiplier    = 0.6

	CritNormal     = 1.1
	CritHighMorale = 1.2
	CritSuper      = 1.3
)

func pilotRatio(attacker, defender Pilot) float64 {
	return math.Max(0, (attacker.Attack-defender.Defense)/5000)
}

func mechRatio(attacker, defender Mech) float64 {
	return math.Max(0, (attacker.Attack/10-defender.Defense/10)/5000)
}

func pilotSigmoid(attacker, defender Pilot) float64 {
	return 1 / (math.Exp(250*(defender.Defense-attacker.Attack)/100000) + 1)
}

func mechSigmoid(attacker, defender Mech) float64 {
	return 1 / (math.Exp(25*(defender.Defense-attacker.Attack)/100000) + 1)
}

func attackCorrection(mech Mech, pilot Pilot) float64 {
	return 100 / (math.Exp((5000-(mech.Attack+pilot.Attack*2)/10)*30/100000) + 1)
}

func defenseCorrection(mech Mech, pilot Pilot) float64 {
	return -40 / (math.Exp((5000-(mech.Defense+pilot.Defense*2)/10)*3/100000) + 1)
}

func BaseDamage(power float64, attacker, defender *Unit) float64 {
	return power * (pilotRatio(attacker.Pilot, defender.Pilot) +
		mechRatio(attacker.Mech, defender.Mech) +
		pilotSigmoid(attacker.Pilot, defender.Pilot) +
		mechSigmoid(attacker.Mech, defender.Mech))
}

func CombatBaseDamage(power float64, attacker, defender *Unit, terrain float64) float64 {
	factor := 1 + attackCorrection(attacker.Mech, attacker.Pilot) +
		defenseCorrection(defender.Mech, defender.Pilot)
	return BaseDamage(power, attacker, defender) * factor / terrain
}

func DamageScale(bonuses, penalties float64) float64 {
	return 1 + bonuses - penalties
}

func FinalDamage(combatBase, scale, defense float64) float64 {
	return combatBase * scale * defense
}

func CriticalDamage(combatBase, scale, defense, critical float64) float64 {
	return FinalDamage(combatBase, scale, defense) * critical
}

func ExpectedDamage(power float64, attacker, defender *Unit,
	terrain, bonuses, penalties, defense float64) float64 {
	return FinalDamage(CombatBaseDamage(power, attacker, defender, terrain),
		DamageScale(bonuses, penalties), defense)
}
