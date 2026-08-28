package formula

import (
	"math"
)

// The damage rules of docs/reference/combat-formulas.md. The unexported
// functions are the corrections 1 to 4, 6 and 7 of that document, and the
// exported ones are the formulas 5 and 8 to 11, plus the composition of the
// formulas 8 to 10. 'rules.go' holds the constants.

func pilotRatio(attacker, defender Side) float64 {
	return math.Max(0, (attacker.PilotAttack-defender.PilotDefense)/5000)
}

func mechRatio(attacker, defender Side) float64 {
	return math.Max(0, (attacker.MechAttack/10-defender.MechDefense/10)/5000)
}

func pilotSigmoid(attacker, defender Side) float64 {
	return 1 / (math.Exp(250*(defender.PilotDefense-attacker.PilotAttack)/100000) + 1)
}

func mechSigmoid(attacker, defender Side) float64 {
	return 1 / (math.Exp(25*(defender.MechDefense-attacker.MechAttack)/100000) + 1)
}

func attackCorrection(attacker Side) float64 {
	return 100 / (math.Exp((5000-(attacker.MechAttack+attacker.PilotAttack*2)/10)*30/100000) + 1)
}

func defenseCorrection(defender Side) float64 {
	return -40 / (math.Exp((5000-(defender.MechDefense+defender.PilotDefense*2)/10)*3/100000) + 1)
}

func BaseDamage(power float64, attacker, defender Side) float64 {
	return power * (pilotRatio(attacker, defender) +
		mechRatio(attacker, defender) +
		pilotSigmoid(attacker, defender) +
		mechSigmoid(attacker, defender))
}

func CombatBaseDamage(power float64, attacker, defender Side, terrain float64) float64 {
	factor := 1 + attackCorrection(attacker) + defenseCorrection(defender)
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

func ExpectedDamage(power float64, attacker, defender Side,
	terrain, bonuses, penalties, defense float64) float64 {
	return FinalDamage(CombatBaseDamage(power, attacker, defender, terrain),
		DamageScale(bonuses, penalties), defense)
}
