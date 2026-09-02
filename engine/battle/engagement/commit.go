package engagement

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// Commit resolves one activation and answers the values column the activation
// leaves. A refusal comes back before the first write.
func Commit(board state.Battle, decision battle.Decision,
	dice battle.Dice) (state.Values, Trace, error) {
	working := board.Values.Clone()
	scratch := state.Battle{Content: board.Content, Values: &working}
	made, err := prepare(scratch, decision)
	if err != nil {
		return state.Values{}, nil, err
	}
	if !dice.Covers(made.draws()) {
		return state.Values{}, nil, fmt.Errorf(
			"%w: the 'outcomes' list holds fewer labels than the %d draws the action can make",
			battle.ErrOutsideContract, made.draws())
	}
	trace := write(scratch, made, dice)
	return working, trace, nil
}

// The write phase writes the plan of the prepare phase. Every rule of the
// exchange is judged there, so nothing here can refuse the plan.
func write(board state.Battle, plan plan, dice battle.Dice) Trace {
	actor := unitOf(board, plan.actorID)
	actor.Value.Pos = plan.anchor
	if plan.kind != battle.ActionAttack {
		endActivation(actor, false)
		return nil
	}
	target := unitOf(board, *plan.targetID)
	weapon := weaponOf(actor, *plan.weaponID)
	actor.Value.EN -= weapon.ENCost
	shot := receiverFor(board, *plan.targetID, plan.answer)
	trace := fire(board, battle.NodeAttackerSupport, StrikeSupport, plan.joining, dice, &shot)
	// The hit rate reads the target of the strike, and not the support defender
	// that takes the strike in its place: the oracle 'decision_hit_probability'
	// reads the target. Which evasion the game reads when a support defender
	// takes the strike is not measured, so the value of the oracle stands until
	// a measurement lands.
	trace = append(trace, shot.hit(StrikeMain, plan.actorID, *plan.weaponID,
		dice.Lands(battle.NodeStrike, strikeHitProbability(actor, target, weapon, plan.answer.dodging()))))
	killed := !unitOf(board, shot.struckID).Alive()

	if plan.answer.response != nil && target.Alive() {
		trace = append(trace, defenderReply(board, plan, dice)...)
	}
	endActivation(actor, killed)
	return trace
}

// The count reads the nodes of the write phase with every unit alive. A kill
// can cut the defender reply short, so the count is an upper bound and never
// falls under the draws that the write phase makes.
func (p plan) draws() int {
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
		if p.answer.counterWeaponID != nil {
			draws++
		}
	}
	return draws
}

func endActivation(actor state.Unit, killed bool) {
	if killed && actor.Alive() && actor.Value.ChanceSteps > 0 {
		actor.Value.ChanceSteps--
		actor.Value.Acted = false
		return
	}
	actor.Value.Acted = true
}

type receiver struct {
	board             state.Battle
	struckID          int
	multiplier        float64
	supportDefenderID *int
	chargeSpent       bool
}

// The support defender of the defender takes the main strike in its place,
// and it takes it in a defense state.
func receiverFor(board state.Battle, targetID int, reply answer) receiver {
	if reply.supportDefenderID != nil {
		return coveredReceiver(board, *reply.supportDefenderID)
	}
	multiplier := formula.NoDefenseMultiplier
	if reply.response != nil {
		multiplier = defenseMultiplier(reply.response.Stance, unitOf(board, targetID))
	}
	return plainReceiver(board, targetID, multiplier)
}

func plainReceiver(board state.Battle, struckID int, multiplier float64) receiver {
	return receiver{board: board, struckID: struckID, multiplier: multiplier}
}

func coveredReceiver(board state.Battle, supportDefenderID int) receiver {
	return receiver{
		board:             board,
		struckID:          supportDefenderID,
		multiplier:        defenseMultiplier(battle.StanceDefend, unitOf(board, supportDefenderID)),
		supportDefenderID: &supportDefenderID,
	}
}

func (v *receiver) hit(kind StrikeKind, shooterID, weaponID int, landed bool) Strike {
	record := Strike{
		Kind:      kind,
		ShooterID: shooterID,
		StruckID:  v.struckID,
		WeaponID:  weaponID,
		Landed:    landed,
	}
	if !landed {
		return record
	}
	if v.supportDefenderID != nil && !v.chargeSpent {
		unitOf(v.board, *v.supportDefenderID).Value.SupportDefendCharges--
		v.chargeSpent = true
	}
	shooter := unitOf(v.board, shooterID)
	struck := unitOf(v.board, v.struckID)
	weapon := weaponOf(shooter, weaponID)
	record.Damage = strikeDamage(shooter, struck, weapon, v.multiplier)
	wound(v.board, struck, weapon, record.Damage)
	record.Killed = !struck.Alive()
	return record
}

// A destroyed unit keeps its place on the board with no hit points left.
// Every roster query filters on Alive.
func wound(board state.Battle, victim state.Unit, weapon *def.Weapon, damage int) {
	victim.Value.HP -= damage
	if victim.Value.HP < 0 {
		victim.Value.HP = 0
	}
	applyDebuff(board, victim, weapon)
}

// The fresh debuff takes the last place of the list, as the frozen goldens
// under tests/fixtures/engine write it.
func applyDebuff(board state.Battle, victim state.Unit, weapon *def.Weapon) {
	kind := weapon.Debuff()
	if kind == "" {
		return
	}
	for index := range victim.Value.Debuffs {
		if victim.Value.Debuffs[index].Kind != kind {
			continue
		}
		if victim.Value.Debuffs[index].Magnitude >= weapon.DebuffMagnitude {
			return
		}
		victim.Value.Debuffs = append(victim.Value.Debuffs[:index], victim.Value.Debuffs[index+1:]...)
		break
	}
	victim.Value.Debuffs = append(victim.Value.Debuffs, battle.Debuff{
		Kind:         kind,
		Magnitude:    weapon.DebuffMagnitude,
		AppliedPhase: board.Values.PhaseIndex(),
	})
}

func defenderReply(board state.Battle, plan plan, dice battle.Dice) Trace {
	var out Trace
	actor := unitOf(board, plan.actorID)
	if len(plan.answer.joining) > 0 && actor.Alive() {
		shot := plainReceiver(board, plan.actorID, formula.NoDefenseMultiplier)
		out = fire(board, battle.NodeDefenderSupport, StrikeDefenderSupport, plan.answer.joining, dice, &shot)
	}
	if plan.answer.counterWeaponID != nil && actor.Alive() {
		out = append(out, counterStrike(board, *plan.targetID, plan.actorID,
			*plan.answer.counterWeaponID, plan.bearerID, dice))
	}
	return out
}

func fire(board state.Battle, node battle.Node, kind StrikeKind, joining []supportAttacker,
	dice battle.Dice, shot *receiver) Trace {
	shooters := able(board, joining)
	if len(shooters) == 0 {
		return nil
	}
	// One die settles the whole support attack, so the probability is the one of
	// the first shot. A die for each support attacker is issue #47.
	first := unitOf(board, shooters[0].UnitID)
	landed := dice.Lands(node, strikeHitProbability(first, unitOf(board, shot.struckID),
		weaponOf(first, shooters[0].WeaponID), false))
	out := make(Trace, 0, len(shooters))
	for _, shooter := range shooters {
		unit := unitOf(board, shooter.UnitID)
		unit.Value.SupportAttackCharges--
		unit.Value.EN -= weaponOf(unit, shooter.WeaponID).ENCost
		out = append(out, shot.hit(kind, shooter.UnitID, shooter.WeaponID, landed))
	}
	return out
}

func able(board state.Battle, joining []supportAttacker) []supportAttacker {
	out := make([]supportAttacker, 0, len(joining))
	for _, one := range joining {
		unit := unitOf(board, one.UnitID)
		if unit.Alive() && unit.Value.SupportAttackCharges > 0 &&
			hasENFor(unit, *weaponOf(unit, one.WeaponID)) {
			out = append(out, one)
		}
	}
	return out
}

// The counter weapon spends its energy on a miss as well.
func counterStrike(board state.Battle, defenderID, attackerID, weaponID int,
	bearerID *int, dice battle.Dice) Strike {
	defender := unitOf(board, defenderID)
	weapon := weaponOf(defender, weaponID)
	defender.Value.EN -= weapon.ENCost
	landed := dice.Lands(battle.NodeCounter,
		strikeHitProbability(defender, unitOf(board, attackerID), weapon, false))
	shot := plainReceiver(board, attackerID, formula.NoDefenseMultiplier)
	if bearerID != nil {
		bearer := unitOf(board, *bearerID)
		if bearer.Alive() && bearer.Value.SupportDefendCharges > 0 {
			shot = coveredReceiver(board, *bearerID)
		}
	}
	return shot.hit(StrikeCounter, defenderID, weaponID, landed)
}
