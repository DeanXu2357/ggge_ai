package battle

import "math"

// The damage rules of docs/reference/combat-formulas.md. The unexported
// functions are the corrections 1 to 4, 6 and 7 of that document, and the
// exported ones are the formulas 5 and 8 to 11. The constants are the
// multipliers the same document lists.
const (
	NoDefenseMultiplier = 1.0
	DefendMultiplier    = 0.8
	ShieldMultiplier    = 0.6

	CritNormal     = 1.1
	CritHighMorale = 1.2
	CritSuper      = 1.3
)

func pilotRatio(pilotAttack, pilotDefense float64) float64 {
	return math.Max(0, (pilotAttack-pilotDefense)/5000)
}

func unitRatio(unitAttack, unitDefense float64) float64 {
	return math.Max(0, (unitAttack/10-unitDefense/10)/5000)
}

func pilotSigmoid(pilotAttack, pilotDefense float64) float64 {
	return 1 / (math.Exp(250*(pilotDefense-pilotAttack)/100000) + 1)
}

func unitSigmoid(unitAttack, unitDefense float64) float64 {
	return 1 / (math.Exp(25*(unitDefense-unitAttack)/100000) + 1)
}

func attackCorrection(unitAttack, pilotAttack float64) float64 {
	return 100 / (math.Exp((5000-(unitAttack+pilotAttack*2)/10)*30/100000) + 1)
}

func defenseCorrection(unitDefense, pilotDefense float64) float64 {
	return -40 / (math.Exp((5000-(unitDefense+pilotDefense*2)/10)*3/100000) + 1)
}

func BaseDamage(power float64, attacker, defender *Unit) float64 {
	return power * (pilotRatio(attacker.PilotAttack, defender.PilotDefense) +
		unitRatio(attacker.UnitAttack, defender.UnitDefense) +
		pilotSigmoid(attacker.PilotAttack, defender.PilotDefense) +
		unitSigmoid(attacker.UnitAttack, defender.UnitDefense))
}

func CombatBaseDamage(power float64, attacker, defender *Unit, terrain float64) float64 {
	factor := 1 + attackCorrection(attacker.UnitAttack, attacker.PilotAttack) +
		defenseCorrection(defender.UnitDefense, defender.PilotDefense)
	return BaseDamage(power, attacker, defender) * factor / terrain
}

func DamageScale(bonuses, penalties float64) float64 {
	return 1 + bonuses - penalties
}

func FinalDamage(combatBase, scale, defense float64) float64 {
	return combatBase * scale * defense
}

func CriticalDamage(combatBase, scale, defense, critical float64) float64 {
	return combatBase * scale * defense * critical
}
