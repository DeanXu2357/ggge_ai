package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
)

// Commit writes the plan of Prepare. Every rule of the exchange is judged
// there, so nothing here can refuse the plan.
func Commit(board *battle.BattleState, plan Plan, dice battle.Dice) Trace {
	plan.actor.Pos = plan.anchor
	if plan.kind != battle.ActionAttack {
		endActivation(plan.actor, false)
		return nil
	}
	plan.actor.EN -= plan.weapon.ENCost
	shot := receiverFor(board, plan.target, plan.answer)
	trace := fire(board, battle.NodeAttackerSupport, StrikeSupport, plan.joining, dice, &shot)
	// The hit rate reads the target of the strike, and not the support defender
	// that takes the strike in its place: the oracle 'decision_hit_probability'
	// reads the target. Which evasion the game reads when a support defender
	// takes the strike is not measured, so the value of the oracle stands until
	// a measurement lands.
	trace = append(trace, shot.hit(StrikeMain, plan.actor, plan.weapon,
		dice.Lands(battle.NodeStrike, strikeHitProbability(plan.actor, plan.target, plan.weapon, plan.answer.dodging()))))
	killed := !shot.struck.Alive()

	if plan.answer.response != nil && plan.target.Alive() {
		trace = append(trace, defenderReply(board, plan, dice)...)
	}
	endActivation(plan.actor, killed)
	return trace
}

// Draws counts the nodes of Commit with every unit alive. A kill can cut the
// defender reply short, so the count is an upper bound and never falls under
// the draws that Commit makes.
func (p Plan) Draws() int {
	if p.kind != battle.ActionAttack {
		return 0
	}
	draws := 1
	if len(p.joining) > 0 {
		draws++
	}
	if p.answer.response != nil {
		if len(p.answer.joining) > 0 {
			draws++
		}
		if p.answer.counter != nil {
			draws++
		}
	}
	return draws
}

func endActivation(actor *battle.Unit, killed bool) {
	if killed && actor.Alive() && actor.ChanceSteps > 0 {
		actor.ChanceSteps--
		actor.Acted = false
		return
	}
	actor.Acted = true
}

type receiver struct {
	board           *battle.BattleState
	struck          *battle.Unit
	multiplier      float64
	supportDefender *battle.Unit
	chargeSpent     bool
}

// The support defender of the defender takes the main strike in its place,
// and it takes it in a defense state.
func receiverFor(board *battle.BattleState, target *battle.Unit, reply answer) receiver {
	if reply.supportDefender != nil {
		return coveredReceiver(board, reply.supportDefender)
	}
	multiplier := formula.NoDefenseMultiplier
	if reply.response != nil {
		multiplier = defenseMultiplier(reply.response.Stance, target)
	}
	return plainReceiver(board, target, multiplier)
}

func plainReceiver(board *battle.BattleState, struck *battle.Unit, multiplier float64) receiver {
	return receiver{board: board, struck: struck, multiplier: multiplier}
}

func coveredReceiver(board *battle.BattleState, supportDefender *battle.Unit) receiver {
	return receiver{
		board:           board,
		struck:          supportDefender,
		multiplier:      defenseMultiplier(battle.StanceDefend, supportDefender),
		supportDefender: supportDefender,
	}
}

func (v *receiver) hit(kind StrikeKind, shooter *battle.Unit, weapon *battle.Weapon, landed bool) Strike {
	record := Strike{
		Kind:      kind,
		ShooterID: shooter.ID,
		StruckID:  v.struck.ID,
		Weapon:    weapon.Name,
		Landed:    landed,
	}
	if !landed {
		return record
	}
	if v.supportDefender != nil && !v.chargeSpent {
		v.supportDefender.SupportDefendCharges--
		v.chargeSpent = true
	}
	record.Damage = strikeDamage(shooter, v.struck, weapon, v.multiplier)
	wound(v.board, v.struck, weapon, record.Damage)
	record.Killed = !v.struck.Alive()
	return record
}

// A destroyed unit keeps its place on the board with no hit points left.
// Every roster query filters on Alive.
func wound(board *battle.BattleState, victim *battle.Unit, weapon *battle.Weapon, damage int) {
	victim.HP -= damage
	if victim.HP < 0 {
		victim.HP = 0
	}
	applyDebuff(board, victim, weapon)
}

// The fresh debuff takes the last place of the list, as the frozen goldens
// under tests/fixtures/engine write it.
func applyDebuff(board *battle.BattleState, victim *battle.Unit, weapon *battle.Weapon) {
	kind := weapon.Debuff()
	if kind == "" {
		return
	}
	for index := range victim.Debuffs {
		if victim.Debuffs[index].Kind != kind {
			continue
		}
		if victim.Debuffs[index].Magnitude >= weapon.DebuffMagnitude {
			return
		}
		victim.Debuffs = append(victim.Debuffs[:index], victim.Debuffs[index+1:]...)
		break
	}
	victim.Debuffs = append(victim.Debuffs, battle.Debuff{
		Kind:         kind,
		Magnitude:    weapon.DebuffMagnitude,
		AppliedPhase: board.PhaseIndex(),
	})
}

func defenderReply(board *battle.BattleState, plan Plan, dice battle.Dice) Trace {
	var out Trace
	if len(plan.answer.joining) > 0 && plan.actor.Alive() {
		shot := plainReceiver(board, plan.actor, formula.NoDefenseMultiplier)
		out = fire(board, battle.NodeDefenderSupport, StrikeDefenderSupport, plan.answer.joining, dice, &shot)
	}
	if plan.answer.counter != nil && plan.actor.Alive() {
		out = append(out, counterStrike(board, plan.target, plan.actor, plan.answer.counter, plan.bearer, dice))
	}
	return out
}

func fire(board *battle.BattleState, node battle.Node, kind StrikeKind, joining []supportAttacker,
	dice battle.Dice, shot *receiver) Trace {
	shooters := able(joining)
	if len(shooters) == 0 {
		return nil
	}
	// One die settles the whole support attack, so the probability is the one of
	// the first shot. A die for each support attacker is issue #47.
	landed := dice.Lands(node, strikeHitProbability(shooters[0].Unit,
		shot.struck, shooters[0].Weapon, false))
	out := make(Trace, 0, len(shooters))
	for _, shooter := range shooters {
		shooter.Unit.SupportAttackCharges--
		shooter.Unit.EN -= shooter.Weapon.ENCost
		out = append(out, shot.hit(kind, shooter.Unit, shooter.Weapon, landed))
	}
	return out
}

func able(joining []supportAttacker) []supportAttacker {
	out := make([]supportAttacker, 0, len(joining))
	for _, one := range joining {
		if one.Unit.Alive() && one.Unit.SupportAttackCharges > 0 &&
			hasENFor(one.Unit, *one.Weapon) {
			out = append(out, one)
		}
	}
	return out
}

// The counter weapon spends its energy on a miss as well.
func counterStrike(board *battle.BattleState, defender, attacker *battle.Unit, weapon *battle.Weapon,
	bearer *battle.Unit, dice battle.Dice) Strike {
	defender.EN -= weapon.ENCost
	landed := dice.Lands(battle.NodeCounter,
		strikeHitProbability(defender, attacker, weapon, false))
	shot := plainReceiver(board, attacker, formula.NoDefenseMultiplier)
	if bearer != nil && bearer.Alive() && bearer.SupportDefendCharges > 0 {
		shot = coveredReceiver(board, bearer)
	}
	return shot.hit(StrikeCounter, defender, weapon, landed)
}
