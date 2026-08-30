package engagement

import (
	"fmt"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const maxSupportAttackers = 3

// Plan carries every choice of one activation with every participant already
// judged. Commit writes it and cannot fail.
type Plan struct {
	kind    ActionKind
	actor   *state.Unit
	anchor  state.Cell
	target  *state.Unit
	weapon  *def.Weapon
	joining []supportAttacker
	bearer  *state.Unit
	answer  answer
}

// A nil response attack stays legal in the domain: it says that the caller
// settles the response attack somewhere else, as a node of a search tree
// does.
type answer struct {
	response        *Response
	counter         *def.Weapon
	supportDefender *state.Unit
	joining         []supportAttacker
}

func (a answer) dodging() bool {
	return a.response != nil && a.response.Stance == StanceDodge
}

// Every rule is judged before the first change of the board, so a refused
// pick leaves the board as it was.
func Prepare(board *state.Board, decision Decision) (Plan, error) {
	actor, err := Activatable(board, decision.UnitID)
	if err != nil {
		return Plan{}, err
	}
	switch decision.Kind {
	case ActionAttack:
		return prepareAttack(board, actor, decision)
	case ActionMapAttack:
		return Plan{}, fmt.Errorf("%w: the engine resolves no map attack, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	case ActionReposition, ActionStandby:
		anchor, err := destination(board, actor, decision.MoveTo, true)
		if err != nil {
			return Plan{}, err
		}
		return Plan{kind: decision.Kind, actor: actor, anchor: anchor}, nil
	}
	return Plan{}, fmt.Errorf("%w: the kind %q is no action of a unit",
		battle.ErrIllegalAction, decision.Kind)
}

func prepareAttack(board *state.Board, actor *state.Unit, decision Decision) (Plan, error) {
	target, err := foe(board, actor, decision.TargetID)
	if err != nil {
		return Plan{}, err
	}
	weapon := weaponOf(actor, decision.Weapon)
	if !directWeapon(weapon) {
		return Plan{}, fmt.Errorf("%w: unit %q carries no attack weapon %q",
			battle.ErrIllegalAction, actor.ID, decision.Weapon)
	}
	if !hasENFor(actor, *weapon) {
		return Plan{}, fmt.Errorf("%w: unit %q cannot pay for the weapon %q",
			battle.ErrIllegalAction, actor.ID, weapon.Name)
	}
	anchor, err := destination(board, actor, decision.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return Plan{}, err
	}
	firing := geometry.FootprintAt(actor, anchor)
	if !weapon.Range.Holds(geometry.Distance(firing, target.Footprint)) {
		return Plan{}, fmt.Errorf("%w: the weapon %q of unit %q does not reach unit %q",
			battle.ErrIllegalAction, weapon.Name, actor.ID, target.ID)
	}
	joining, err := namedSupportAttackers(board, actor, firing, target.Footprint,
		decision.SupportAttackers)
	if err != nil {
		return Plan{}, err
	}
	bearer, err := namedSupportDefendWhenAttack(board, actor, firing, decision.SupportDefender)
	if err != nil {
		return Plan{}, err
	}
	answer, err := answerOf(board, target, firing, decision.Response)
	if err != nil {
		return Plan{}, err
	}
	return Plan{
		kind:    ActionAttack,
		actor:   actor,
		anchor:  anchor,
		target:  target,
		weapon:  weapon,
		joining: joining,
		bearer:  bearer,
		answer:  answer,
	}, nil
}

func Activatable(board *state.Board, unitID string) (*state.Unit, error) {
	unit, err := LivingUnit(board, unitID)
	if err != nil {
		return nil, err
	}
	if err := OnPhase(board, unit); err != nil {
		return nil, err
	}
	if unit.Acted {
		return nil, fmt.Errorf("%w: %q", battle.ErrActed, unitID)
	}
	return unit, nil
}

// LivingUnit and OnPhase are the two gates that every command reads, so the
// shell asks them here and no package writes the refusal twice.
func LivingUnit(board *state.Board, id string) (*state.Unit, error) {
	unit := board.Unit(id)
	if unit == nil {
		return nil, fmt.Errorf("%w: %q", battle.ErrNoUnit, id)
	}
	if !unit.Alive() {
		return nil, fmt.Errorf("%w: %q", battle.ErrDestroyed, id)
	}
	return unit, nil
}

func OnPhase(board *state.Board, unit *state.Unit) error {
	if unit.Faction != board.Phase {
		return fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			battle.ErrOffPhase, unit.ID, unit.Faction, board.Phase)
	}
	return nil
}

func foe(board *state.Board, actor *state.Unit, targetID string) (*state.Unit, error) {
	target, err := LivingUnit(board, targetID)
	if err != nil {
		return nil, err
	}
	if target.Faction != actor.Faction.Opposing() {
		return nil, fmt.Errorf("%w: unit %q of the side %q is no foe of unit %q",
			battle.ErrIllegalAction, target.ID, target.Faction, actor.ID)
	}
	return target, nil
}

func destination(board *state.Board, actor *state.Unit, to *state.Cell, permitted bool) (state.Cell, error) {
	if to == nil {
		return actor.Footprint.Anchor, nil
	}
	if !permitted {
		return state.Cell{}, fmt.Errorf("%w: the action of unit %q runs before a move",
			battle.ErrIllegalMove, actor.ID)
	}
	if !geometry.ReachableAnchors(board, actor)[*to] {
		return state.Cell{}, fmt.Errorf("%w: unit %q does not reach the anchor %v",
			battle.ErrIllegalMove, actor.ID, *to)
	}
	return *to, nil
}

func answerOf(board *state.Board, defender *state.Unit, firing state.Footprint,
	response *Response) (answer, error) {
	if response == nil {
		return answer{}, nil
	}
	out := answer{response: response}
	if !knownStances[response.Stance] {
		return answer{}, fmt.Errorf("%w: unit %q takes the stance %q, which is not in the contract",
			battle.ErrIllegalAction, defender.ID, response.Stance)
	}
	if response.Stance == StanceCounter {
		out.counter = counterWeapon(defender, response.Weapon, firing)
		if out.counter == nil {
			return answer{}, fmt.Errorf("%w: unit %q counters the strike with no weapon %q",
				battle.ErrIllegalAction, defender.ID, response.Weapon)
		}
	} else if response.Weapon != "" {
		return answer{}, fmt.Errorf("%w: the stance %q of unit %q fires no weapon",
			battle.ErrIllegalAction, response.Stance, defender.ID)
	}
	supportDefender, err := namedSupportDefender(board, defender, defender.Footprint, response.SupportDefender,
		func(*state.Unit) bool { return true })
	if err != nil {
		return answer{}, err
	}
	// A defender that defends blocks the strike for itself and leaves the
	// supportDefender nothing to take (docs/reference/battle-prep-ui.md:279, issue
	// #44). Whether the game pairs a support defender with the stand is not
	// measured; the engine permits it until a measurement lands.
	if supportDefender != nil && response.Stance == StanceDefend {
		return answer{}, fmt.Errorf("%w: unit %q defends the strike itself and takes no support defender",
			battle.ErrIllegalAction, defender.ID)
	}
	out.supportDefender = supportDefender
	if out.joining, err = namedSupportAttackers(board, defender, defender.Footprint, firing,
		response.SupportAttackers); err != nil {
		return answer{}, err
	}
	return out, nil
}

func namedSupportAttackers(board *state.Board, supported *state.Unit, firing, foe state.Footprint,
	names []string) ([]supportAttacker, error) {
	if len(names) == 0 {
		return nil, nil
	}
	if limit := maxSupportAttackers; len(names) > limit {
		return nil, fmt.Errorf("%w: unit %q names %d support attackers, and the rules permit %d",
			battle.ErrIllegalAction, supported.ID, len(names), limit)
	}
	eligible := supportAttackers(board, supported, firing, foe)
	out := make([]supportAttacker, 0, len(names))
	for _, name := range names {
		if slices.ContainsFunc(out, func(one supportAttacker) bool { return one.Unit.ID == name }) {
			return nil, fmt.Errorf("%w: unit %q joins the strike of unit %q two times",
				battle.ErrIllegalAction, name, supported.ID)
		}
		index := slices.IndexFunc(eligible, func(one supportAttacker) bool {
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

func namedSupportDefender(board *state.Board, covered *state.Unit, at state.Footprint, name string,
	fits func(*state.Unit) bool) (*state.Unit, error) {
	if name == "" {
		return nil, nil
	}
	for _, other := range supportDefenders(board, covered, at) {
		if other.ID == name && fits(other) {
			return other, nil
		}
	}
	return nil, fmt.Errorf("%w: unit %q takes no strike for unit %q",
		battle.ErrIllegalAction, name, covered.ID)
}

func namedSupportDefendWhenAttack(board *state.Board, actor *state.Unit, firing state.Footprint,
	name string) (*state.Unit, error) {
	return namedSupportDefender(board, actor, firing, name,
		func(other *state.Unit) bool { return other.SupportDefendWhenAttack })
}
