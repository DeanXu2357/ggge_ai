package system

import (
	"fmt"
	"math/rand/v2"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type exchange struct {
	board   state.Battle
	draw    *rand.Rand
	actorID int
	cast    cast
	paid    map[int]bool // the support defenders that paid their charge in this exchange
	killed  bool         // a strike of the attacker side destroyed a unit
}

func (x *exchange) attackContext(attacker, struck unit, weapon *def.Weapon) ability.AttackContext {
	a := ability.AttackContext{Attacker: attacker.toAbilityUnit(x.cast.part(attacker.id)),
		Defender: struck.toAbilityUnit(x.cast.part(struck.id)), Weapon: weapon}
	attacker.Value.Hooks.Attack(&a)
	return a
}

func (x *exchange) defendContext(attacker, defender unit, weapon *def.Weapon) ability.DefendContext {
	d := ability.DefendContext{Attacker: attacker.toAbilityUnit(x.cast.part(attacker.id)),
		Defender: defender.toAbilityUnit(x.cast.part(defender.id)), Weapon: weapon}
	defender.Value.Hooks.Defend(&d)
	return d
}

// The owner decides whether a strike fires, not the shooter: a support
// attacker of a destroyed unit lives, and its strike does not fire.
func (x *exchange) fire(s strike) battle.StrikeEvent {
	event := battle.StrikeEvent{Kind: battle.EventStrike, Segment: s.segment,
		ShooterID: s.shooterID, WeaponID: s.weaponID, AimedID: s.aimedID, StruckID: s.struckID}
	if !unitOf(x.board, s.ownerID).Alive() {
		event.Reason = fmt.Sprintf("unit %d is destroyed", s.ownerID)
		event.Effects = []battle.Effect{}
		return event
	}
	event.Fired = true

	shooter, aimed, struck := unitOf(x.board, s.shooterID), unitOf(x.board, s.aimedID), unitOf(x.board, s.struckID)
	a := x.attackContext(shooter, struck, s.weapon)
	aimedDefense := x.defendContext(shooter, aimed, s.weapon)
	struckDefense := aimedDefense
	if s.struckID != s.aimedID {
		struckDefense = x.defendContext(shooter, struck, s.weapon)
	}

	event.Landed, event.Critical = x.behaviors(s, a, aimedDefense)

	var led ledger
	if event.Landed {
		event.Damage = damageOf(a, struckDefense, defenseMultiplier(s.stance, struck))
		if struck.Alive() {
			led.unit(s.struckID).HP = change(&struck.Value.HP, max(0, struck.Value.HP-event.Damage))
			if s.weapon.DebuffKind != nil {
				fresh := battle.Debuff{Kind: *s.weapon.DebuffKind, Magnitude: s.weapon.DebuffMagnitude,
					AppliedPhase: x.board.Values.PhaseIndex()}
				led.unit(s.struckID).Debuffs = changeDebuffs(&struck.Value.Debuffs, applied(struck.Value.Debuffs, fresh))
			}
			if struck.Value.HP == 0 && s.ownerID == x.actorID {
				x.killed = true
			}
		}
		if s.struckID != s.aimedID && !x.paid[s.struckID] {
			x.paid[s.struckID] = true
			led.unit(s.struckID).SupportDefendCharges = change(&struck.Value.SupportDefendCharges, struck.Value.SupportDefendCharges-1)
		}
	}
	if cost := enCostOf(shooter, x.cast.part(s.shooterID), s.weapon); cost > 0 {
		led.unit(s.shooterID).EN = change(&shooter.Value.EN, shooter.Value.EN-cost)
	}
	if s.shooterID != s.ownerID {
		led.unit(s.shooterID).SupportAttackCharges = change(&shooter.Value.SupportAttackCharges, shooter.Value.SupportAttackCharges-1)
	}
	event.Effects = led.list()
	return event
}

// No rule computes a critical rate, so a drawn critical is false.
func (x *exchange) behaviors(s strike, a ability.AttackContext, d ability.DefendContext) (landed, critical bool) {
	if s.stated != nil {
		return s.stated.Hit, s.stated.Crit
	}
	return x.draw.Float64() < hitRateOf(a, d, s.dodging), false
}

func applied(debuffs []battle.Debuff, fresh battle.Debuff) []battle.Debuff {
	out := make([]battle.Debuff, 0, len(debuffs)+1)
	for _, debuff := range debuffs {
		if debuff.Kind != fresh.Kind {
			out = append(out, debuff)
			continue
		}
		if debuff.Magnitude > fresh.Magnitude {
			fresh = debuff
		}
	}
	return append(out, fresh)
}
