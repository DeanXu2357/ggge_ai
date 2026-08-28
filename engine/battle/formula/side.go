package formula

// The fields are the symbols of docs/reference/combat-formulas.md: PlAtk,
// PlDef, UnAtk and UnDef, plus the reaction and the mobility of the hit rate.
type Side struct {
	PilotAttack   float64
	PilotDefense  float64
	PilotReaction float64
	MechAttack    float64
	MechDefense   float64
	Mobility      float64
}
