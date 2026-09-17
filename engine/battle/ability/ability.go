// Package ability is the contract between the engine and the effect lines a
// unit carries. A line is a value that holds its numbers and its own state,
// and implements the hook of each moment it acts in; when a unit takes its
// lines, each hook goes on the chain of its moment, and the engine runs the
// chain of a moment with the context of that moment.
package ability

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

// Line is one effect line of a unit. Clone answers a copy with the same
// state, so that a copy of the value column owns its lines.
type Line interface {
	Clone() Line
}

// Part is what a unit is in the exchange, the same for every strike of it:
// the unit that started the exchange, the unit it was started against, or
// a unit that supports either side. Whether a supporter fires or takes a
// strike is the slot it holds in the strike; which strike fires first is
// the flow of the exchange (a weapon may strike first on the counter); a
// line reads the part and neither of those.
type Part string

const (
	PartAttacker Part = "attacker" // started the exchange
	PartTarget   Part = "target"   // the exchange was started against it
	PartSupport  Part = "support"  // fires or takes a strike for another unit
)

// Unit is what a hook sees of one unit: its data, the values of the moment,
// and what it does in this strike.
type Unit struct {
	Mech    *def.Mech
	Pilot   *def.Pilot
	HP      int
	MaxHP   int
	Debuffs []battle.Debuff
	Part    Part
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
	// AccuracyPercent is added to the hit rate in points ("Increase own
	// ACC by 5%" is 5 points; that the game reads it so is a hypothesis of
	// the roadmap).
	AccuracyPercent float64
}

// DefendContext is the input of a defend hook: the strike the defender takes.
// The aimed unit defends the hit roll, the struck unit the damage; they are
// one unit unless a support defender covers.
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
	// EvasionPercent is taken off the hit rate of the strike in points.
	EvasionPercent float64
}

type WeaponCostContext struct {
	Shooter Unit
	Weapon  *def.Weapon

	// ENCostPercent is the signed change of the EN cost: -20 is a fifth
	// less.
	ENCostPercent float64
}

// AssembleContext is the input of an assembly hook: the unit as it enters
// the battle. The engine derives the allowances of the unit, how many times
// it may support attack, support defend and act again after a kill, from a
// base and these sums, one time on every assembly.
type AssembleContext struct {
	Unit Unit

	SupportAttackPlus int
	SupportDefendPlus int
	ChanceStepPlus    int
	MaxHPPercent      float64
	MaxENPercent      float64
	MoveRangePlus     int
	MPPlus            int
}

type AttackHook func(a *AttackContext)

type DefendHook func(d *DefendContext)

type WeaponCostHook func(w *WeaponCostContext)

type AssembleHook func(a *AssembleContext)

type AttackUnitHook interface {
	OnAttack(a *AttackContext)
}

type DefendUnitHook interface {
	OnDefend(d *DefendContext)
}

type WeaponCostUnitHook interface {
	OnWeaponCost(w *WeaponCostContext)
}

type AssembleUnitHook interface {
	OnAssemble(a *AssembleContext)
}

// Hooks is the chains of one unit. A chain runs in the order of the lines.
type Hooks struct {
	OnAttack     []AttackHook
	OnDefend     []DefendHook
	OnWeaponCost []WeaponCostHook
	OnAssemble   []AssembleHook
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
		if hook, acts := line.(WeaponCostUnitHook); acts {
			h.OnWeaponCost = append(h.OnWeaponCost, hook.OnWeaponCost)
		}
		if hook, acts := line.(AssembleUnitHook); acts {
			h.OnAssemble = append(h.OnAssemble, hook.OnAssemble)
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

func (h Hooks) WeaponCost(w *WeaponCostContext) {
	for _, hook := range h.OnWeaponCost {
		hook(w)
	}
}

func (h Hooks) Assemble(a *AssembleContext) {
	for _, hook := range h.OnAssemble {
		hook(a)
	}
}
