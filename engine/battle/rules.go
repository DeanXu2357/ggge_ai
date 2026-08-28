package battle

// The rules of the mechanism. Every value here holds for the whole title: no
// stage changes one, so none of them reaches the wire. The user ruled on
// 2026-08-26 that a stage that needs a different number does not exist, and
// that a rule which does vary is an ability of a unit or of a weapon.
//
// docs/reference/combat-formulas.md holds the source of each value.
const (
	NoDefenseMultiplier = 1.0
	NoTerrainCorrection = 1.0

	// A shield is a second cut on top of the defense, and not a stance of its
	// own: a shielded defender pays DefendMultiplier and ShieldMultiplier both.
	DefendMultiplier = 0.8
	ShieldMultiplier = 0.8

	CritNormal     = 1.1
	CritHighMorale = 1.2
	CritSuper      = 1.3

	DodgeHitPenalty     = 20.0
	MaxSupportAttackers = 3
	ENRegenPercent      = 10
)

// The response attack menu offers no shield stance, so a defender that
// carries a shield defends with the shield here, in the damage (issue #63).
func StanceMultiplier(stance Stance, defender *Unit) float64 {
	if stance != StanceDefend {
		return NoDefenseMultiplier
	}
	if defender.HasShield {
		return ShieldMultiplier * DefendMultiplier
	}
	return DefendMultiplier
}
