package battle

import (
	"errors"
	"fmt"
	"slices"
)

var (
	ErrIllegalAction = errors.New("the action is not legal")
	ErrIllegalMove   = errors.New("the move is not legal")
)

type StrikeKind string

const (
	StrikeSupport         StrikeKind = "support"
	StrikeMain            StrikeKind = "strike"
	StrikeDefenderSupport StrikeKind = "defender_support"
	StrikeCounter         StrikeKind = "counter"
)

// The Damage of a skill record is the value that the skill gave back.
type Strike struct {
	Kind      StrikeKind
	ShooterID string
	StruckID  string
	Weapon    string
	Landed    bool
	Damage    int
	Killed    bool
}

type Trace []Strike

type outcome struct {
	killed         bool
	endsActivation bool
}

func (b *Board) Apply(decision Decision, dice Dice) (Trace, error) {
	actor, err := b.Activatable(decision.UnitID)
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

func (b *Board) run(actor *Unit, decision Decision, dice Dice) (Trace, outcome, error) {
	switch decision.Kind {
	case ActionAttack:
		return b.attack(actor, decision, dice)
	case ActionMapAttack:
		return nil, outcome{}, fmt.Errorf("%w: the engine resolves no map attack, because the area of a map weapon is not in the contract",
			ErrIllegalAction)
	case ActionReposition, ActionStandby:
		anchor, err := b.destination(actor, decision.MoveTo, true)
		if err != nil {
			return nil, outcome{}, err
		}
		actor.Footprint.Anchor = anchor
		return nil, outcome{endsActivation: true}, nil
	}
	return nil, outcome{}, fmt.Errorf("%w: the kind %q is no action of a unit",
		ErrIllegalAction, decision.Kind)
}

func endActivation(actor *Unit, end outcome) {
	if end.killed && actor.Alive() && actor.ChanceSteps > 0 {
		actor.ChanceSteps--
		actor.Acted = false
		return
	}
	actor.Acted = end.endsActivation
}

func (b *Board) destination(actor *Unit, to *Cell, permitted bool) (Cell, error) {
	if to == nil {
		return actor.Footprint.Anchor, nil
	}
	if !permitted {
		return Cell{}, fmt.Errorf("%w: the action of unit %q runs before a move",
			ErrIllegalMove, actor.ID)
	}
	if !b.reachableAnchors(actor)[*to] {
		return Cell{}, fmt.Errorf("%w: unit %q does not reach the anchor %v",
			ErrIllegalMove, actor.ID, *to)
	}
	return *to, nil
}

// Every rule is judged before the first change of the board, so a refused
// pick leaves the board as it was.
func (b *Board) attack(actor *Unit, decision Decision, dice Dice) (Trace, outcome, error) {
	target, err := b.foe(actor, decision.TargetID)
	if err != nil {
		return nil, outcome{}, err
	}
	weapon := actor.Weapon(decision.Weapon)
	if weapon == nil || weapon.MapWeapon {
		return nil, outcome{}, fmt.Errorf("%w: unit %q carries no attack weapon %q",
			ErrIllegalAction, actor.ID, decision.Weapon)
	}
	if !actor.HasENFor(*weapon) {
		return nil, outcome{}, fmt.Errorf("%w: unit %q cannot pay for the weapon %q",
			ErrIllegalAction, actor.ID, weapon.Name)
	}
	anchor, err := b.destination(actor, decision.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return nil, outcome{}, err
	}
	firing := footprintAt(actor, anchor)
	if !weapon.Range.Holds(SpanDistance(firing, target.Footprint)) {
		return nil, outcome{}, fmt.Errorf("%w: the weapon %q of unit %q does not reach unit %q",
			ErrIllegalAction, weapon.Name, actor.ID, target.ID)
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
	trace := b.fire(NodeAttackerSupport, StrikeSupport, joining, dice, &shot)
	dodging := answer.responseAttack != nil && answer.responseAttack.Stance == StanceDodge
	// The hit rate reads the target of the strike, and not the support defender
	// that takes the strike in its place: the oracle 'decision_hit_probability'
	// reads the target. Which evasion the game reads when a support defender
	// takes the strike is not measured, so the value of the oracle stands until
	// a measurement lands.
	trace = append(trace, shot.hit(StrikeMain, actor, weapon,
		dice.Lands(NodeStrike, StrikeHitProbability(actor, target, weapon, dodging))))
	killed := !shot.struck.Alive()

	if answer.responseAttack != nil && target.Alive() {
		trace = append(trace, b.defenderReply(actor, target, answer, bearer, dice)...)
	}
	return trace, outcome{killed: killed, endsActivation: true}, nil
}

func (b *Board) foe(actor *Unit, targetID string) (*Unit, error) {
	target, err := b.livingUnit(targetID)
	if err != nil {
		return nil, err
	}
	if target.Faction != actor.Faction.Opposing() {
		return nil, fmt.Errorf("%w: unit %q of the side %q is no foe of unit %q",
			ErrIllegalAction, target.ID, target.Faction, actor.ID)
	}
	return target, nil
}

// A nil response attack stays legal in the domain: it says that the caller
// settles the response attack somewhere else, as a node of a search tree
// does.
type answer struct {
	responseAttack  *ResponseAttack
	counter         *Weapon
	supportDefender *Unit
	joining         []SupportAttacker
}

func (b *Board) answerOf(defender, attacker *Unit, firing Footprint,
	responseAttack *ResponseAttack) (answer, error) {
	if responseAttack == nil {
		return answer{}, nil
	}
	out := answer{responseAttack: responseAttack}
	if _, known := wireStances[responseAttack.Stance]; !known {
		return answer{}, fmt.Errorf("%w: unit %q takes the stance %q, which is not in the contract",
			ErrIllegalAction, defender.ID, responseAttack.Stance)
	}
	if responseAttack.Stance == StanceCounter {
		out.counter = b.CounterWeapon(defender, responseAttack.Weapon, firing)
		if out.counter == nil {
			return answer{}, fmt.Errorf("%w: unit %q counters the strike with no weapon %q",
				ErrIllegalAction, defender.ID, responseAttack.Weapon)
		}
	} else if responseAttack.Weapon != "" {
		return answer{}, fmt.Errorf("%w: the stance %q of unit %q fires no weapon",
			ErrIllegalAction, responseAttack.Stance, defender.ID)
	}
	supportDefender, err := b.namedSupportDefender(defender, defender.Footprint, responseAttack.SupportDefender,
		func(*Unit) bool { return true })
	if err != nil {
		return answer{}, err
	}
	// A defender that defends blocks the strike for itself and leaves the
	// supportDefender nothing to take (docs/reference/battle-prep-ui.md:279, issue
	// #44). Whether the game pairs a support defender with the stand is not
	// measured; the engine permits it until a measurement lands.
	if supportDefender != nil && responseAttack.Stance == StanceDefend {
		return answer{}, fmt.Errorf("%w: unit %q defends the strike itself and takes no support defender",
			ErrIllegalAction, defender.ID)
	}
	out.supportDefender = supportDefender
	if out.joining, err = b.namedSupportAttackers(defender, defender.Footprint, firing,
		responseAttack.SupportAttackers); err != nil {
		return answer{}, err
	}
	return out, nil
}

func (b *Board) namedSupportAttackers(supported *Unit, firing, foe Footprint,
	names []string) ([]SupportAttacker, error) {
	if len(names) == 0 {
		return nil, nil
	}
	if limit := MaxSupportAttackers; len(names) > limit {
		return nil, fmt.Errorf("%w: unit %q names %d support attackers, and the rules permit %d",
			ErrIllegalAction, supported.ID, len(names), limit)
	}
	eligible := b.SupportAttackers(supported, firing, foe)
	out := make([]SupportAttacker, 0, len(names))
	for _, name := range names {
		if slices.ContainsFunc(out, func(one SupportAttacker) bool { return one.Unit.ID == name }) {
			return nil, fmt.Errorf("%w: unit %q joins the strike of unit %q two times",
				ErrIllegalAction, name, supported.ID)
		}
		index := slices.IndexFunc(eligible, func(one SupportAttacker) bool {
			return one.Unit.ID == name
		})
		if index < 0 {
			return nil, fmt.Errorf("%w: unit %q cannot join the strike of unit %q",
				ErrIllegalAction, name, supported.ID)
		}
		out = append(out, eligible[index])
	}
	return out, nil
}

func (b *Board) namedSupportDefender(covered *Unit, at Footprint, name string,
	fits func(*Unit) bool) (*Unit, error) {
	if name == "" {
		return nil, nil
	}
	for _, other := range b.SupportDefenders(covered, at) {
		if other.ID == name && fits(other) {
			return other, nil
		}
	}
	return nil, fmt.Errorf("%w: unit %q takes no strike for unit %q",
		ErrIllegalAction, name, covered.ID)
}

func (b *Board) namedSupportDefendWhenAttack(actor *Unit, firing Footprint, name string) (*Unit, error) {
	return b.namedSupportDefender(actor, firing, name,
		func(other *Unit) bool { return other.SupportDefendWhenAttack })
}

type receiver struct {
	board           *Board
	struck          *Unit
	multiplier      float64
	supportDefender *Unit
	chargeSpent     bool
}

func (b *Board) receiverOf(target *Unit, answer answer) receiver {
	if answer.supportDefender != nil {
		return b.coveredReceiver(answer.supportDefender)
	}
	multiplier := NoDefenseMultiplier
	if answer.responseAttack != nil {
		multiplier = StanceMultiplier(answer.responseAttack.Stance, target)
	}
	return b.plainReceiver(target, multiplier)
}

func (b *Board) plainReceiver(struck *Unit, multiplier float64) receiver {
	return receiver{board: b, struck: struck, multiplier: multiplier}
}

func (b *Board) coveredReceiver(supportDefender *Unit) receiver {
	return receiver{
		board:           b,
		struck:          supportDefender,
		multiplier:      StanceMultiplier(StanceDefend, supportDefender),
		supportDefender: supportDefender,
	}
}

func (v *receiver) hit(kind StrikeKind, shooter *Unit, weapon *Weapon, landed bool) Strike {
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
	record.Damage = StrikeDamage(shooter, v.struck, weapon, v.multiplier)
	v.board.wound(v.struck, weapon, record.Damage)
	record.Killed = !v.struck.Alive()
	return record
}

// A destroyed unit keeps its place on the board with no hit points left.
// Every roster query filters on Alive.
func (b *Board) wound(victim *Unit, weapon *Weapon, damage int) {
	victim.HP -= damage
	if victim.HP < 0 {
		victim.HP = 0
	}
	b.applyDebuff(victim, weapon)
}

// The fresh debuff takes the last place of the list, as the frozen goldens
// under tests/fixtures/engine write it.
func (b *Board) applyDebuff(victim *Unit, weapon *Weapon) {
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
	victim.Debuffs = append(victim.Debuffs, Debuff{
		Kind:         weapon.DebuffKind,
		Magnitude:    weapon.DebuffMagnitude,
		AppliedPhase: b.PhaseIndex(),
	})
}

func (b *Board) defenderReply(actor, target *Unit, answer answer, bearer *Unit,
	dice Dice) Trace {
	var out Trace
	if len(answer.joining) > 0 && actor.Alive() {
		shot := b.plainReceiver(actor, NoDefenseMultiplier)
		out = b.fire(NodeDefenderSupport, StrikeDefenderSupport, answer.joining, dice, &shot)
	}
	if answer.counter != nil && actor.Alive() {
		out = append(out, b.counterStrike(target, actor, answer.counter, bearer, dice))
	}
	return out
}

func (b *Board) fire(node Node, kind StrikeKind, joining []SupportAttacker, dice Dice,
	shot *receiver) Trace {
	shooters := able(joining)
	if len(shooters) == 0 {
		return nil
	}
	// One die settles the whole support attack, so the probability is the one of
	// the first shot. A die for each support attacker is issue #47.
	landed := dice.Lands(node, StrikeHitProbability(shooters[0].Unit,
		shot.struck, shooters[0].Weapon, false))
	out := make(Trace, 0, len(shooters))
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
func (b *Board) counterStrike(defender, attacker *Unit, weapon *Weapon, bearer *Unit,
	dice Dice) Strike {
	defender.EN -= weapon.ENCost
	landed := dice.Lands(NodeCounter,
		StrikeHitProbability(defender, attacker, weapon, false))
	shot := b.plainReceiver(attacker, NoDefenseMultiplier)
	if bearer != nil && bearer.Alive() && bearer.SupportDefendCharges > 0 {
		shot = b.coveredReceiver(bearer)
	}
	return shot.hit(StrikeCounter, defender, weapon, landed)
}
