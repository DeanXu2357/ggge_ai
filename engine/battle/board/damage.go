package board

import (
	"math"
)

// The damage rules of docs/reference/combat-formulas.md. The unexported
// functions are the corrections 1 to 4, 6 and 7 of that document, and the
// exported ones are the formulas 5 and 8 to 11, plus the composition of the
// formulas 8 to 10. 'rules.go' holds the constants.

func pilotRatio(attack float64, defender Pilot) float64 {
	return math.Max(0, (attack-defender.Defense)/5000)
}

func mechRatio(attacker, defender Mech) float64 {
	return math.Max(0, (attacker.Attack/10-defender.Defense/10)/5000)
}

func pilotSigmoid(attack float64, defender Pilot) float64 {
	return 1 / (math.Exp(250*(defender.Defense-attack)/100000) + 1)
}

func mechSigmoid(attacker, defender Mech) float64 {
	return 1 / (math.Exp(25*(defender.Defense-attacker.Attack)/100000) + 1)
}

func attackCorrection(mech Mech, pilotAttack float64) float64 {
	return 100 / (math.Exp((5000-(mech.Attack+pilotAttack*2)/10)*30/100000) + 1)
}

func defenseCorrection(mech Mech, pilot Pilot) float64 {
	return -40 / (math.Exp((5000-(mech.Defense+pilot.Defense*2)/10)*3/100000) + 1)
}

func BaseDamage(weapon Weapon, attacker, defender *Unit) float64 {
	attack := attacker.Pilot.AttackFor(weapon)
	return weapon.Power * (pilotRatio(attack, defender.Pilot) +
		mechRatio(attacker.Mech, defender.Mech) +
		pilotSigmoid(attack, defender.Pilot) +
		mechSigmoid(attacker.Mech, defender.Mech))
}

func CombatBaseDamage(weapon Weapon, attacker, defender *Unit, terrain float64) float64 {
	factor := 1 + attackCorrection(attacker.Mech, attacker.Pilot.AttackFor(weapon)) +
		defenseCorrection(defender.Mech, defender.Pilot)
	return BaseDamage(weapon, attacker, defender) * factor / terrain
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

func ExpectedDamage(weapon Weapon, attacker, defender *Unit,
	terrain, bonuses, penalties, defense float64) float64 {
	return FinalDamage(CombatBaseDamage(weapon, attacker, defender, terrain),
		DamageScale(bonuses, penalties), defense)
}
