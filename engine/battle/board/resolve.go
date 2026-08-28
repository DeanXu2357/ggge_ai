package board

import (
	"fmt"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

type outcome struct {
	killed         bool
	endsActivation bool
}

func (b *Board) Apply(decision battle.Decision, dice battle.Dice) (battle.Trace, error) {
	actor, err := b.activatable(decision.UnitID)
	if err != nil {
		return nil, err
	}
	trace, end, err := b.run(actor, decision, dice)
	if err != nil {
		return nil, err
	}
	endActivation(actor, end)
	return trace, nil
}

func (b *Board) run(actor *battle.Unit, decision battle.Decision, dice battle.Dice) (battle.Trace, outcome, error) {
	switch decision.Kind {
	case battle.ActionAttack:
		return b.attack(actor, decision, dice)
	case battle.ActionMapAttack:
		return nil, outcome{}, fmt.Errorf("%w: the engine resolves no map attack, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	case battle.ActionReposition, battle.ActionStandby:
		anchor, err := b.destination(actor, decision.MoveTo, true)
		if err != nil {
			return nil, outcome{}, err
		}
		actor.Footprint.Anchor = anchor
		return nil, outcome{endsActivation: true}, nil
	}
	return nil, outcome{}, fmt.Errorf("%w: the kind %q is no action of a unit",
		battle.ErrIllegalAction, decision.Kind)
}

func endActivation(actor *battle.Unit, end outcome) {
	if end.killed && actor.Alive() && actor.ChanceSteps > 0 {
		actor.ChanceSteps--
		actor.Acted = false
		return
	}
	actor.Acted = end.endsActivation
}

func (b *Board) destination(actor *battle.Unit, to *battle.Cell, permitted bool) (battle.Cell, error) {
	if to == nil {
		return actor.Footprint.Anchor, nil
	}
	if !permitted {
		return battle.Cell{}, fmt.Errorf("%w: the action of unit %q runs before a move",
			battle.ErrIllegalMove, actor.ID)
	}
	if !b.reachableAnchors(actor)[*to] {
		return battle.Cell{}, fmt.Errorf("%w: unit %q does not reach the anchor %v",
			battle.ErrIllegalMove, actor.ID, *to)
	}
	return *to, nil
}

// Every rule is judged before the first change of the board, so a refused
// pick leaves the board as it was.
func (b *Board) attack(actor *battle.Unit, decision battle.Decision, dice battle.Dice) (battle.Trace, outcome, error) {
	target, err := b.foe(actor, decision.TargetID)
	if err != nil {
		return nil, outcome{}, err
	}
	weapon := actor.Weapon(decision.Weapon)
	if weapon == nil || weapon.MapWeapon {
		return nil, outcome{}, fmt.Errorf("%w: unit %q carries no attack weapon %q",
			battle.ErrIllegalAction, actor.ID, decision.Weapon)
	}
	if !actor.HasENFor(*weapon) {
		return nil, outcome{}, fmt.Errorf("%w: unit %q cannot pay for the weapon %q",
			battle.ErrIllegalAction, actor.ID, weapon.Name)
	}
	anchor, err := b.destination(actor, decision.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return nil, outcome{}, err
	}
	firing := footprintAt(actor, anchor)
	if !weapon.Range.Holds(SpanDistance(firing, target.Footprint)) {
		return nil, outcome{}, fmt.Errorf("%w: the weapon %q of unit %q does not reach unit %q",
			battle.ErrIllegalAction, weapon.Name, actor.ID, target.ID)
	}
	joining, err := b.namedSupportAttackers(actor, firing, target.Footprint,
		decision.SupportAttackers)
	if err != nil {
		return nil, outcome{}, err
	}
	bearer, err := b.namedSupportDefendWhenAttack(actor, firing, decision.SupportDefender)
	if err != nil {
		return nil, outcome{}, err
	}
	answer, err := b.answerOf(target, actor, firing, decision.ResponseAttack)
	if err != nil {
		return nil, outcome{}, err
	}

	actor.Footprint.Anchor = anchor
	actor.EN -= weapon.ENCost
	shot := b.receiverOf(target, answer)
	trace := b.fire(battle.NodeAttackerSupport, battle.StrikeSupport, joining, dice, &shot)
	dodging := answer.responseAttack != nil && answer.responseAttack.Stance == battle.StanceDodge
	// The hit rate reads the target of the strike, and not the support defender
	// that takes the strike in its place: the oracle 'decision_hit_probability'
	// reads the target. Which evasion the game reads when a support defender
	// takes the strike is not measured, so the value of the oracle stands until
	// a measurement lands.
	trace = append(trace, shot.hit(battle.StrikeMain, actor, weapon,
		dice.Lands(battle.NodeStrike, StrikeHitProbability(actor, target, weapon, dodging))))
	killed := !shot.struck.Alive()

	if answer.responseAttack != nil && target.Alive() {
		trace = append(trace, b.defenderReply(actor, target, answer, bearer, dice)...)
	}
	return trace, outcome{killed: killed, endsActivation: true}, nil
}

func (b *Board) foe(actor *battle.Unit, targetID string) (*battle.Unit, error) {
	target, err := b.livingUnit(targetID)
	if err != nil {
		return nil, err
	}
	if target.Faction != actor.Faction.Opposing() {
		return nil, fmt.Errorf("%w: unit %q of the side %q is no foe of unit %q",
			battle.ErrIllegalAction, target.ID, target.Faction, actor.ID)
	}
	return target, nil
}

// A nil response attack stays legal in the domain: it says that the caller
// settles the response attack somewhere else, as a node of a search tree
// does.
type answer struct {
	responseAttack  *battle.ResponseAttack
	counter         *battle.Weapon
	supportDefender *battle.Unit
	joining         []SupportAttacker
}

func (b *Board) answerOf(defender, attacker *battle.Unit, firing battle.Footprint,
	responseAttack *battle.ResponseAttack) (answer, error) {
	if responseAttack == nil {
		return answer{}, nil
	}
	out := answer{responseAttack: responseAttack}
	if _, known := wireStances[responseAttack.Stance]; !known {
		return answer{}, fmt.Errorf("%w: unit %q takes the stance %q, which is not in the contract",
			battle.ErrIllegalAction, defender.ID, responseAttack.Stance)
	}
	if responseAttack.Stance == battle.StanceCounter {
		out.counter = b.counterWeapon(defender, responseAttack.Weapon, firing)
		if out.counter == nil {
			return answer{}, fmt.Errorf("%w: unit %q counters the strike with no weapon %q",
				battle.ErrIllegalAction, defender.ID, responseAttack.Weapon)
		}
	} else if responseAttack.Weapon != "" {
		return answer{}, fmt.Errorf("%w: the stance %q of unit %q fires no weapon",
			battle.ErrIllegalAction, responseAttack.Stance, defender.ID)
	}
	supportDefender, err := b.namedSupportDefender(defender, defender.Footprint, responseAttack.SupportDefender,
		func(*battle.Unit) bool { return true })
	if err != nil {
		return answer{}, err
	}
	// A defender that defends blocks the strike for itself and leaves the
	// supportDefender nothing to take (docs/reference/battle-prep-ui.md:279, issue
	// #44). Whether the game pairs a support defender with the stand is not
	// measured; the engine permits it until a measurement lands.
	if supportDefender != nil && responseAttack.Stance == battle.StanceDefend {
		return answer{}, fmt.Errorf("%w: unit %q defends the strike itself and takes no support defender",
			battle.ErrIllegalAction, defender.ID)
	}
	out.supportDefender = supportDefender
	if out.joining, err = b.namedSupportAttackers(defender, defender.Footprint, firing,
		responseAttack.SupportAttackers); err != nil {
		return answer{}, err
	}
	return out, nil
}

func (b *Board) namedSupportAttackers(supported *battle.Unit, firing, foe battle.Footprint,
	names []string) ([]SupportAttacker, error) {
	if len(names) == 0 {
		return nil, nil
	}
	if limit := MaxSupportAttackers; len(names) > limit {
		return nil, fmt.Errorf("%w: unit %q names %d support attackers, and the rules permit %d",
			battle.ErrIllegalAction, supported.ID, len(names), limit)
	}
	eligible := b.supportAttackers(supported, firing, foe)
	out := make([]SupportAttacker, 0, len(names))
	for _, name := range names {
		if slices.ContainsFunc(out, func(one SupportAttacker) bool { return one.Unit.ID == name }) {
			return nil, fmt.Errorf("%w: unit %q joins the strike of unit %q two times",
				battle.ErrIllegalAction, name, supported.ID)
		}
		index := slices.IndexFunc(eligible, func(one SupportAttacker) bool {
			return one.Unit.ID == name
		})
		if index < 0 {
			return nil, fmt.Errorf("%w: unit %q cannot join the strike of unit %q",
				battle.ErrIllegalAction, name, supported.ID)
		}
		out = append(out, eligible[index])
	}
	return out, nil
}

func (b *Board) namedSupportDefender(covered *battle.Unit, at battle.Footprint, name string,
	fits func(*battle.Unit) bool) (*battle.Unit, error) {
	if name == "" {
		return nil, nil
	}
	for _, other := range b.supportDefenders(covered, at) {
		if other.ID == name && fits(other) {
			return other, nil
		}
	}
	return nil, fmt.Errorf("%w: unit %q takes no strike for unit %q",
		battle.ErrIllegalAction, name, covered.ID)
}

func (b *Board) namedSupportDefendWhenAttack(actor *battle.Unit, firing battle.Footprint, name string) (*battle.Unit, error) {
	return b.namedSupportDefender(actor, firing, name,
		func(other *battle.Unit) bool { return other.SupportDefendWhenAttack })
}

type receiver struct {
	board           *Board
	struck          *battle.Unit
	multiplier      float64
	supportDefender *battle.Unit
	chargeSpent     bool
}

func (b *Board) receiverOf(target *battle.Unit, answer answer) receiver {
	if answer.supportDefender != nil {
		return b.coveredReceiver(answer.supportDefender)
	}
	multiplier := NoDefenseMultiplier
	if answer.responseAttack != nil {
		multiplier = StanceMultiplier(answer.responseAttack.Stance, target)
	}
	return b.plainReceiver(target, multiplier)
}

func (b *Board) plainReceiver(struck *battle.Unit, multiplier float64) receiver {
	return receiver{board: b, struck: struck, multiplier: multiplier}
}

func (b *Board) coveredReceiver(supportDefender *battle.Unit) receiver {
	return receiver{
		board:           b,
		struck:          supportDefender,
		multiplier:      StanceMultiplier(battle.StanceDefend, supportDefender),
		supportDefender: supportDefender,
	}
}

func (v *receiver) hit(kind battle.StrikeKind, shooter *battle.Unit, weapon *battle.Weapon, landed bool) battle.Strike {
	record := battle.Strike{
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
	record.Damage = StrikeDamage(shooter, v.struck, weapon, v.multiplier)
	v.board.wound(v.struck, weapon, record.Damage)
	record.Killed = !v.struck.Alive()
	return record
}

// A destroyed unit keeps its place on the board with no hit points left.
// Every roster query filters on Alive.
func (b *Board) wound(victim *battle.Unit, weapon *battle.Weapon, damage int) {
	victim.HP -= damage
	if victim.HP < 0 {
		victim.HP = 0
	}
	b.applyDebuff(victim, weapon)
}

// The fresh debuff takes the last place of the list, as the frozen goldens
// under tests/fixtures/engine write it.
func (b *Board) applyDebuff(victim *battle.Unit, weapon *battle.Weapon) {
	if weapon.DebuffKind == "" {
		return
	}
	for index := range victim.Debuffs {
		if victim.Debuffs[index].Kind != weapon.DebuffKind {
			continue
		}
		if victim.Debuffs[index].Magnitude >= weapon.DebuffMagnitude {
			return
		}
		victim.Debuffs = append(victim.Debuffs[:index], victim.Debuffs[index+1:]...)
		break
	}
	victim.Debuffs = append(victim.Debuffs, battle.Debuff{
		Kind:         weapon.DebuffKind,
		Magnitude:    weapon.DebuffMagnitude,
		AppliedPhase: b.phaseIndex(),
	})
}

func (b *Board) defenderReply(actor, target *battle.Unit, answer answer, bearer *battle.Unit,
	dice battle.Dice) battle.Trace {
	var out battle.Trace
	if len(answer.joining) > 0 && actor.Alive() {
		shot := b.plainReceiver(actor, NoDefenseMultiplier)
		out = b.fire(battle.NodeDefenderSupport, battle.StrikeDefenderSupport, answer.joining, dice, &shot)
	}
	if answer.counter != nil && actor.Alive() {
		out = append(out, b.counterStrike(target, actor, answer.counter, bearer, dice))
	}
	return out
}

func (b *Board) fire(node battle.Node, kind battle.StrikeKind, joining []SupportAttacker, dice battle.Dice,
	shot *receiver) battle.Trace {
	shooters := able(joining)
	if len(shooters) == 0 {
		return nil
	}
	// One die settles the whole support attack, so the probability is the one of
	// the first shot. A die for each support attacker is issue #47.
	landed := dice.Lands(node, StrikeHitProbability(shooters[0].Unit,
		shot.struck, shooters[0].Weapon, false))
	out := make(battle.Trace, 0, len(shooters))
	for _, shooter := range shooters {
		shooter.Unit.SupportAttackCharges--
		shooter.Unit.EN -= shooter.Weapon.ENCost
		out = append(out, shot.hit(kind, shooter.Unit, shooter.Weapon, landed))
	}
	return out
}

func able(joining []SupportAttacker) []SupportAttacker {
	out := make([]SupportAttacker, 0, len(joining))
	for _, one := range joining {
		if one.Unit.Alive() && one.Unit.SupportAttackCharges > 0 &&
			one.Unit.HasENFor(*one.Weapon) {
			out = append(out, one)
		}
	}
	return out
}

// The counter weapon spends its energy on a miss as well.
func (b *Board) counterStrike(defender, attacker *battle.Unit, weapon *battle.Weapon, bearer *battle.Unit,
	dice battle.Dice) battle.Strike {
	defender.EN -= weapon.ENCost
	landed := dice.Lands(battle.NodeCounter,
		StrikeHitProbability(defender, attacker, weapon, false))
	shot := b.plainReceiver(attacker, NoDefenseMultiplier)
	if bearer != nil && bearer.Alive() && bearer.SupportDefendCharges > 0 {
		shot = b.coveredReceiver(bearer)
	}
	return shot.hit(battle.StrikeCounter, defender, weapon, landed)
}
