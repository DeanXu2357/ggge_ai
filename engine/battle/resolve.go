package battle

import (
	"errors"
	"fmt"
	"math"
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
	StrikeSkill           StrikeKind = "skill"
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
	case ActionSkillHeal, ActionSkillRefill:
		return b.skill(actor, decision)
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
	bearer, err := b.namedAttackShield(actor, firing, decision.SupportDefender)
	if err != nil {
		return nil, outcome{}, err
	}
	answer, err := b.answerOf(target, actor, firing, decision.Reaction)
	if err != nil {
		return nil, outcome{}, err
	}

	actor.Footprint.Anchor = anchor
	actor.EN -= weapon.ENCost
	shot := b.receiverOf(target, answer)
	trace := b.fire(NodeAttackerSupport, StrikeSupport, joining, dice, &shot)
	dodging := answer.reaction != nil && answer.reaction.Stance == StanceDodge
	// The hit rate reads the target of the strike, and not the interceptor that
	// takes the strike in its place: the oracle 'decision_hit_probability' reads
	// the target. Which evasion the game reads on an interception is not
	// measured, so the value of the oracle stands until a measurement lands.
	trace = append(trace, shot.hit(StrikeMain, actor, weapon,
		dice.Lands(NodeStrike, StrikeHitProbability(actor, target, weapon, dodging))))
	killed := !shot.struck.Alive()

	if answer.reaction != nil && target.Alive() {
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

// A nil reaction stays legal in the domain: it says that the caller settles
// the reaction somewhere else, as a node of a search tree does.
type answer struct {
	reaction    *Reaction
	counter     *Weapon
	interceptor *Unit
	joining     []SupportAttacker
}

func (b *Board) answerOf(defender, attacker *Unit, firing Footprint,
	reaction *Reaction) (answer, error) {
	if reaction == nil {
		return answer{}, nil
	}
	out := answer{reaction: reaction}
	if _, known := wireStances[reaction.Stance]; !known {
		return answer{}, fmt.Errorf("%w: unit %q takes the stance %q, which is not in the contract",
			ErrIllegalAction, defender.ID, reaction.Stance)
	}
	if reaction.Stance == StanceCounter {
		out.counter = b.CounterWeapon(defender, reaction.Weapon, firing)
		if out.counter == nil {
			return answer{}, fmt.Errorf("%w: unit %q counters the strike with no weapon %q",
				ErrIllegalAction, defender.ID, reaction.Weapon)
		}
	} else if reaction.Weapon != "" {
		return answer{}, fmt.Errorf("%w: the stance %q of unit %q fires no weapon",
			ErrIllegalAction, reaction.Stance, defender.ID)
	}
	interceptor, err := b.namedInterceptor(defender, defender.Footprint, reaction.SupportDefender,
		func(*Unit) bool { return true })
	if err != nil {
		return answer{}, err
	}
	// A defender that defends blocks the strike for itself and leaves the
	// interceptor nothing to take (docs/reference/battle-prep-ui.md:279, issue
	// #44). Whether the game pairs an interceptor with the stand is not
	// measured; the engine permits it until a measurement lands.
	if interceptor != nil && reaction.Stance == StanceDefend {
		return answer{}, fmt.Errorf("%w: unit %q defends the strike itself and takes no interceptor",
			ErrIllegalAction, defender.ID)
	}
	out.interceptor = interceptor
	if out.joining, err = b.namedSupportAttackers(defender, defender.Footprint, firing,
		reaction.SupportAttackers); err != nil {
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

func (b *Board) namedInterceptor(covered *Unit, at Footprint, name string,
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

func (b *Board) namedAttackShield(actor *Unit, firing Footprint, name string) (*Unit, error) {
	return b.namedInterceptor(actor, firing, name,
		func(other *Unit) bool { return other.AttackShield })
}

type receiver struct {
	board       *Board
	struck      *Unit
	multiplier  float64
	interceptor *Unit
	chargeSpent bool
}

func (b *Board) receiverOf(target *Unit, answer answer) receiver {
	if answer.interceptor != nil {
		return b.interceptedReceiver(answer.interceptor)
	}
	multiplier := NoDefenseMultiplier
	if answer.reaction != nil {
		multiplier = StanceMultiplier(answer.reaction.Stance, target)
	}
	return b.plainReceiver(target, multiplier)
}

func (b *Board) plainReceiver(struck *Unit, multiplier float64) receiver {
	return receiver{board: b, struck: struck, multiplier: multiplier}
}

func (b *Board) interceptedReceiver(interceptor *Unit) receiver {
	return receiver{
		board:       b,
		struck:      interceptor,
		multiplier:  InterceptionMultiplier(interceptor),
		interceptor: interceptor,
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
	if v.interceptor != nil && !v.chargeSpent {
		v.interceptor.SupportDefendCharges--
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
		shot = b.interceptedReceiver(bearer)
	}
	return shot.hit(StrikeCounter, defender, weapon, landed)
}

// The model carries only the skill whose area is the cell of the caster, so
// the caster is the one legal target of the decision.
func (b *Board) skill(actor *Unit, decision Decision) (Trace, outcome, error) {
	if decision.TargetID != "" && decision.TargetID != actor.ID {
		return nil, outcome{}, fmt.Errorf("%w: the skill %q of unit %q reaches no unit %q",
			ErrIllegalAction, decision.Kind, actor.ID, decision.TargetID)
	}
	skill := actor.Skill(decision.Kind, decision.Amount)
	if skill == nil {
		return nil, outcome{}, fmt.Errorf("%w: unit %q holds no skill %q of that amount with a use left",
			ErrIllegalAction, actor.ID, decision.Kind)
	}
	anchor, err := b.destination(actor, decision.MoveTo, skill.UsableAfterMove)
	if err != nil {
		return nil, outcome{}, err
	}

	actor.Footprint.Anchor = anchor
	skill.Uses--
	record := Strike{Kind: StrikeSkill, ShooterID: actor.ID, StruckID: actor.ID, Landed: true}
	switch decision.Kind {
	case ActionSkillHeal:
		record.Damage = gain(actor.HP, actor.MaxHP, skill.Amount)
		actor.HP += record.Damage
	case ActionSkillRefill:
		record.Damage = gain(actor.EN, actor.ENMax, skill.Amount)
		actor.EN += record.Damage
	}
	return Trace{record}, outcome{endsActivation: skill.EndsActivation}, nil
}

// The amount comes from the wire as a float, so a value that no integer
// holds gives the whole room, and a value below zero gives nothing.
func gain(value, limit int, amount *float64) int {
	room := max(0, limit-value)
	if amount == nil || math.IsNaN(*amount) || *amount >= float64(room) {
		return room
	}
	if *amount < 0 {
		return 0
	}
	return int(*amount)
}
