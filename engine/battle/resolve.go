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

// StrikeKind names the place of one record in the order of one engagement
// (docs/reference/combat-formulas.md, the section of the resolution order).
type StrikeKind string

const (
	StrikeSupport         StrikeKind = "support"
	StrikeMain            StrikeKind = "strike"
	StrikeDefenderSupport StrikeKind = "defender_support"
	StrikeCounter         StrikeKind = "counter"
	StrikeMap             StrikeKind = "map"
	StrikeSkill           StrikeKind = "skill"
)

// A Strike is one shot of one resolution. The Damage of a skill record is the
// value that the skill gave back.
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

// outcome carries what the bookkeeping of the activation reads.
type outcome struct {
	killed         bool
	endsActivation bool
}

// Apply runs one decision on the board and gives the trace of the engagement.
// The move comes first and the action second: every effect reads the anchor
// after the move (docs/spec/battle-engine-protocol.md). An error leaves the
// board as it was.
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
		trace, err := b.mapAttack(actor, decision)
		return trace, outcome{endsActivation: true}, err
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

// A kill gives the attacker its whole activation again while it holds a chance
// step left (docs/reference/combat-formulas.md, case 5 and case 19).
func endActivation(actor *Unit, end outcome) {
	if end.killed && actor.Alive() && actor.ChanceSteps > 0 {
		actor.ChanceSteps--
		actor.Acted = false
		return
	}
	actor.Acted = end.endsActivation
}

// destination gives the anchor that the actor stands on after the move of the
// decision. The weapon or the skill of the action holds the permission to move
// in the same activation.
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
	if !actor.CanPay(weapon) {
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
	if err := b.legalReaction(target, actor, anchor, weapon, decision.Reaction); err != nil {
		return nil, outcome{}, err
	}
	counter, err := b.counterOf(target, firing, decision.Reaction)
	if err != nil {
		return nil, outcome{}, err
	}

	actor.Footprint.Anchor = anchor
	actor.EN -= weapon.ENCost
	shot := b.volleyOn(target, decision.Reaction)
	trace := b.attackerVolley(actor, target, decision.Support, dice, &shot)
	dodging := decision.Reaction != nil && decision.Reaction.Stance == StanceDodge
	// The hit rate reads the target of the strike, and not the interceptor that
	// takes the strike in its place: the oracle 'decision_hit_probability' reads
	// the target. Which evasion the game reads on an interception is not
	// measured, so the value of the oracle stands until a measurement lands.
	trace = append(trace, shot.hit(StrikeMain, actor, weapon,
		dice.Lands(NodeStrike, StrikeHitProbability(actor, target, weapon, dodging, b.Rules))))
	killed := !shot.struck.Alive()

	if decision.Reaction != nil && target.Alive() {
		trace = append(trace, b.defenderReply(actor, target, *decision.Reaction, counter, dice)...)
	}
	return trace, outcome{killed: killed, endsActivation: true}, nil
}

// foe gives the living unit of the opposing side that the strike names. The
// faction rule is the one of TargetsOf, so a unit strikes at what the
// enumeration offers it, and never at itself or at a unit of its own side.
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

// legalReaction refuses a reaction that the command 'reactions' does not give
// for this strike. A nil reaction stays legal in the domain: it says that the
// caller settles the reaction somewhere else, as a node of a search tree does
// (docs/spec/battle-engine-protocol.md, the wire rules of the reaction).
func (b *Board) legalReaction(defender, attacker *Unit, anchor Cell, weapon *Weapon,
	reaction *Reaction) error {
	if reaction == nil {
		return nil
	}
	options, err := b.Reactions(defender.ID, attacker.ID, anchor, weapon.Name)
	if err != nil {
		return fmt.Errorf("%w: %s", ErrIllegalAction, err)
	}
	if slices.Contains(options, *reaction) {
		return nil
	}
	return fmt.Errorf("%w: unit %q takes a reaction that \"reactions\" does not give: %+v",
		ErrIllegalAction, defender.ID, *reaction)
}

func (b *Board) counterOf(defender *Unit, attacker Footprint, reaction *Reaction) (*Weapon, error) {
	if reaction == nil || reaction.Stance != StanceCounter {
		return nil, nil
	}
	weapon := b.CounterWeapon(defender, reaction.Weapon, attacker)
	if weapon == nil {
		return nil, fmt.Errorf("%w: unit %q counters the strike with no weapon %q",
			ErrIllegalAction, defender.ID, reaction.Weapon)
	}
	return weapon, nil
}

// volley carries the unit that takes the shots of one attack. Every landed hit
// of the whole volley goes to that unit, and an interceptor spends one charge
// on the first landed hit (docs/reference/combat-formulas.md, case 12 and 13).
type volley struct {
	board       *Board
	struck      *Unit
	multiplier  float64
	interceptor *Unit
	chargeSpent bool
}

func (b *Board) volleyOn(target *Unit, reaction *Reaction) volley {
	if reaction != nil && reaction.SupportDefend {
		if interceptor := b.SupportDefender(target); interceptor != nil {
			return b.interceptedVolley(interceptor)
		}
	}
	multiplier := NoDefenseMultiplier
	if reaction != nil {
		multiplier = b.Rules.StanceMultiplier(reaction.Stance)
	}
	return b.plainVolley(target, multiplier)
}

func (b *Board) plainVolley(struck *Unit, multiplier float64) volley {
	return volley{board: b, struck: struck, multiplier: multiplier}
}

func (b *Board) interceptedVolley(interceptor *Unit) volley {
	return volley{
		board:       b,
		struck:      interceptor,
		multiplier:  b.Rules.InterceptionMultiplier(interceptor),
		interceptor: interceptor,
	}
}

func (v *volley) hit(kind StrikeKind, shooter *Unit, weapon *Weapon, landed bool) Strike {
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
	record.Damage = StrikeDamage(shooter, v.struck, weapon, v.multiplier, v.board.Rules)
	v.board.wound(v.struck, weapon, record.Damage)
	record.Killed = !v.struck.Alive()
	return record
}

// A destroyed unit keeps its place on the board with no hit points left. Every
// roster query filters on Alive.
func (b *Board) wound(victim *Unit, weapon *Weapon, damage int) {
	victim.HP -= damage
	if victim.HP < 0 {
		victim.HP = 0
	}
	b.applyDebuff(victim, weapon)
}

// A debuff of the same kind replaces a weaker one and leaves a stronger one
// alone (docs/reference/combat-formulas.md, case 11). The fresh debuff takes
// the last place of the list, as the oracle writes it.
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

// The attacker chooses the support attack, and its volley fires before the
// main strike (docs/reference/combat-formulas.md, case 13).
func (b *Board) attackerVolley(actor, target *Unit, support bool, dice Dice, shot *volley) Trace {
	if !support {
		return nil
	}
	return b.fire(NodeSupportVolley, StrikeSupport,
		b.supportersOf(actor, actor.Footprint, target.Footprint), dice, shot)
}

// The volley of the defender fires after the strike of the attacker, so a
// supporter that the strike destroyed or drained fires nothing.
func (b *Board) defenderReply(actor, target *Unit, reaction Reaction, counter *Weapon,
	dice Dice) Trace {
	var out Trace
	if reaction.SupportAttack && actor.Alive() {
		shot := b.plainVolley(actor, NoDefenseMultiplier)
		out = b.fire(NodeDefenderVolley, StrikeDefenderSupport,
			b.supportersOf(target, target.Footprint, actor.Footprint), dice, &shot)
	}
	if counter != nil && actor.Alive() {
		out = append(out, b.counterStrike(target, actor, counter, dice))
	}
	return out
}

func (b *Board) fire(node Node, kind StrikeKind, supporters []SupportAttacker, dice Dice,
	shot *volley) Trace {
	if len(supporters) == 0 {
		return nil
	}
	// One die settles the whole volley, so the probability is the one of the
	// first shot. A die for each supporter is issue #47.
	landed := dice.Lands(node, StrikeHitProbability(supporters[0].Unit,
		shot.struck, supporters[0].Weapon, false, b.Rules))
	out := make(Trace, 0, len(supporters))
	for _, supporter := range supporters {
		supporter.Unit.SupportAttackCharges--
		supporter.Unit.EN -= supporter.Weapon.ENCost
		out = append(out, shot.hit(kind, supporter.Unit, supporter.Weapon, landed))
	}
	return out
}

// The rules cap the number of supporters that join one strike
// (docs/reference/combat-formulas.md, case 9a).
func (b *Board) supportersOf(supported *Unit, firing, foe Footprint) []SupportAttacker {
	out := b.SupportAttackers(supported, firing, foe)
	if limit := max(0, b.Rules.MaxSupportAttackers); len(out) > limit {
		out = out[:limit]
	}
	return out
}

// The counter weapon spends its energy on a miss as well.
func (b *Board) counterStrike(defender, attacker *Unit, weapon *Weapon, dice Dice) Strike {
	defender.EN -= weapon.ENCost
	landed := dice.Lands(NodeCounter,
		StrikeHitProbability(defender, attacker, weapon, false, b.Rules))
	shot := b.plainVolley(attacker, NoDefenseMultiplier)
	if bearer := b.AttackShieldBearer(attacker); bearer != nil {
		shot = b.interceptedVolley(bearer)
	}
	return shot.hit(StrikeCounter, defender, weapon, landed)
}

// A map strike reaches every foe of the blast, and it settles no chance node:
// it always lands, it draws no reaction and no interception
// (docs/reference/combat-formulas.md, case 23 to 25).
func (b *Board) mapAttack(actor *Unit, decision Decision) (Trace, error) {
	weapon := actor.Weapon(decision.Weapon)
	if weapon == nil || !weapon.MapWeapon {
		return nil, fmt.Errorf("%w: unit %q carries no map weapon %q",
			ErrIllegalAction, actor.ID, decision.Weapon)
	}
	if decision.Aim == nil {
		return nil, fmt.Errorf("%w: the map attack of unit %q names no aim cell",
			ErrIllegalAction, actor.ID)
	}
	if actor.Ammo[weapon.Name] <= 0 || !actor.CanPay(weapon) {
		return nil, fmt.Errorf("%w: unit %q cannot fire the weapon %q",
			ErrIllegalAction, actor.ID, weapon.Name)
	}
	anchor, err := b.destination(actor, decision.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return nil, err
	}
	aim := cellFootprint(*decision.Aim)
	if !weapon.Range.Holds(SpanDistance(footprintAt(actor, anchor), aim)) {
		return nil, fmt.Errorf("%w: the weapon %q of unit %q does not reach the cell %v",
			ErrIllegalAction, weapon.Name, actor.ID, *decision.Aim)
	}

	actor.Footprint.Anchor = anchor
	actor.Ammo[weapon.Name]--
	actor.EN -= weapon.ENCost
	var out Trace
	for _, victim := range b.TargetsOf(actor) {
		if SpanDistance(victim.Footprint, aim) > weapon.Blast {
			continue
		}
		shot := b.plainVolley(victim, NoDefenseMultiplier)
		out = append(out, shot.hit(StrikeMap, actor, weapon, true))
	}
	return out, nil
}

// The enumeration gives only the skill whose area is the cell of the caster, so
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

// A skill with no amount gives the whole room up to the maximum. The amount
// comes from the wire as a float, so a value that no integer holds gives the
// room as well, and a value below zero gives nothing.
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
