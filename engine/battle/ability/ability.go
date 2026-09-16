// Package ability is the contract between the engine and the effect lines a
// unit carries. A line is a value that holds its numbers and its own state,
// and implements the hook of each moment it acts in; when a unit takes its
// lines, each hook goes on the chain of its moment, and the engine runs the
// chain of a moment with the context of that moment.
package ability

import "github.com/DeanXu2357/ggge_ai/engine/battle/def"

// Line is one effect line of a unit. Clone answers a copy with the same
// state, so that a copy of the value column owns its lines.
type Line interface {
	Clone() Line
}

// Unit is what a hook sees of one unit: its data and the values of the
// moment.
type Unit struct {
	Mech  *def.Mech
	Pilot *def.Pilot
	HP    int
	MaxHP int
}

// AttackContext is the input of an attack hook: the strike the attacker fires. Every hook of the
// attacker adds its share to the percent of a stat; the engine multiplies
// the base one time, so the order of the chain does not change the result.
//
// Defender is the unit on the other end of the computation: the aimed unit
// for the hit rate, the struck unit for the damage. The two differ when a
// support defender covers the target.
type AttackContext struct {
	Attacker Unit
	Defender Unit
	Weapon   *def.Weapon

	MechAttackPercent   float64
	MechMobilityPercent float64
	PilotRangedPercent  float64
	PilotMeleePercent   float64
	PilotAwakenPercent  float64
	// DamageDealtPercent is the signed change of the damage dealt: 15 is
	// 15 percent more. It joins the sum of ⑨ with the damage taken of the
	// defender and its debuffs.
	DamageDealtPercent float64
}

// DefendContext is the input of a defend hook: the strike the defender takes.
// Defender is the holder of the hooks; see AttackContext for which unit it is.
type DefendContext struct {
	Attacker Unit
	Defender Unit
	Weapon   *def.Weapon

	MechDefensePercent   float64
	MechMobilityPercent  float64
	PilotDefensePercent  float64
	PilotReactionPercent float64
	// DamageTakenPercent is the signed change of the damage taken: -50 is
	// half the damage. It joins the sum of ⑨ with the debuffs of the unit.
	DamageTakenPercent float64
}

type AttackHook func(a *AttackContext)

type DefendHook func(d *DefendContext)

type AttackUnitHook interface {
	OnAttack(a *AttackContext)
}

type DefendUnitHook interface {
	OnDefend(d *DefendContext)
}

// Hooks is the chains of one unit. A chain runs in the order of the lines.
type Hooks struct {
	OnAttack []AttackHook
	OnDefend []DefendHook
}

// HooksOf binds the hook methods of the lines. The chains point at these
// lines, so a copy of the lines takes its own chains.
func HooksOf(lines []Line) Hooks {
	var h Hooks
	for _, line := range lines {
		if hook, acts := line.(AttackUnitHook); acts {
			h.OnAttack = append(h.OnAttack, hook.OnAttack)
		}
		if hook, acts := line.(DefendUnitHook); acts {
			h.OnDefend = append(h.OnDefend, hook.OnDefend)
		}
	}
	return h
}

func CloneLines(lines []Line) []Line {
	if lines == nil {
		return nil
	}
	out := make([]Line, len(lines))
	for index, line := range lines {
		out[index] = line.Clone()
	}
	return out
}

func (h Hooks) Attack(a *AttackContext) {
	for _, hook := range h.OnAttack {
		hook(a)
	}
}

func (h Hooks) Defend(d *DefendContext) {
	for _, hook := range h.OnDefend {
		hook(d)
	}
}
