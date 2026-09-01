package engagement

import (
	"fmt"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const maxSupportAttackers = 3

// Plan carries every choice of one activation with every participant already
// judged. Commit writes it and cannot fail.
type Plan struct {
	kind     battle.ActionKind
	actorID  int
	anchor   battle.Cell
	targetID *int
	weaponID *int
	joining  []supportAttacker
	bearerID *int
	answer   answer
}

// A nil response attack stays legal in the domain: it says that the caller
// settles the response attack somewhere else, as a node of a search tree
// does.
type answer struct {
	response          *battle.ResponseAttack
	counterWeaponID   *int
	supportDefenderID *int
	joining           []supportAttacker
}

func (a answer) dodging() bool {
	return a.response != nil && a.response.Stance == battle.StanceDodge
}

// Every rule is judged before the first change of the board, so a refused
// action leaves the board as it was.
func Prepare(board *state.Battle, decision battle.Decision) (Plan, error) {
	actor, err := Activatable(board, decision.UnitID)
	if err != nil {
		return Plan{}, err
	}
	if err := checkIDs(board, decision); err != nil {
		return Plan{}, err
	}
	switch decision.Kind {
	case battle.ActionAttack:
		return prepareAttack(board, decision, actor)
	case battle.ActionMapAttack:
		return Plan{}, fmt.Errorf("%w: the engine resolves no map attack, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	case battle.ActionReposition, battle.ActionStandby:
		anchor, err := destination(board, decision.UnitID, decision.MoveTo, true)
		if err != nil {
			return Plan{}, err
		}
		return Plan{kind: decision.Kind, actorID: decision.UnitID, anchor: anchor}, nil
	}
	return Plan{}, fmt.Errorf("%w: the kind %q is no action of a unit",
		battle.ErrIllegalAction, decision.Kind)
}

// checkIDs bounds-checks every id that the wire carries, one time, before the
// first write. Past this gate an id names a thing of the board.
func checkIDs(board *state.Battle, decision battle.Decision) error {
	actor, err := board.UnitAt(decision.UnitID)
	if err != nil {
		return err
	}
	for _, id := range unitIDsOf(decision) {
		if _, err := board.UnitAt(id); err != nil {
			return err
		}
	}
	if decision.WeaponID != nil {
		if _, err := actor.WeaponAt(*decision.WeaponID); err != nil {
			return err
		}
	}
	if decision.MapWeaponID != nil {
		if _, err := actor.MapWeaponAt(*decision.MapWeaponID); err != nil {
			return err
		}
	}
	if err := checkCounterWeaponID(board, decision); err != nil {
		return err
	}
	return checkArmament(decision)
}

func unitIDsOf(decision battle.Decision) []int {
	out := slices.Clone(decision.SupportAttackerIDs)
	if decision.TargetID != nil {
		out = append(out, *decision.TargetID)
	}
	if decision.SupportDefenderID != nil {
		out = append(out, *decision.SupportDefenderID)
	}
	if response := decision.ResponseAttack; response != nil {
		out = append(out, response.SupportAttackerIDs...)
		if response.SupportDefenderID != nil {
			out = append(out, *response.SupportDefenderID)
		}
	}
	return out
}

// The weapon of a response attack belongs to the unit that the action strikes.
func checkCounterWeaponID(board *state.Battle, decision battle.Decision) error {
	response := decision.ResponseAttack
	if response == nil || response.WeaponID == nil {
		return nil
	}
	if decision.TargetID == nil {
		return fmt.Errorf("%w: the response attack fires a weapon and the action names no target",
			battle.ErrIllegalAction)
	}
	defender, err := board.UnitAt(*decision.TargetID)
	if err != nil {
		return err
	}
	_, err = defender.WeaponAt(*response.WeaponID)
	return err
}

func checkArmament(decision battle.Decision) error {
	weapon, mapWeapon := decision.WeaponID != nil, decision.MapWeaponID != nil
	if decision.Kind != battle.ActionAttack {
		if weapon || mapWeapon {
			return fmt.Errorf("%w: an action of the kind %q fires no weapon",
				battle.ErrIllegalAction, decision.Kind)
		}
		return nil
	}
	if weapon && mapWeapon {
		return fmt.Errorf("%w: the attack names a weapon and a map weapon",
			battle.ErrIllegalAction)
	}
	if !weapon && !mapWeapon {
		return fmt.Errorf("%w: the attack names no weapon", battle.ErrIllegalAction)
	}
	return nil
}

func prepareAttack(board *state.Battle, decision battle.Decision, actor *state.Unit) (Plan, error) {
	if decision.MapWeaponID != nil {
		return Plan{}, fmt.Errorf("%w: the engine fires no map weapon, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	}
	targetID, err := foe(board, decision.UnitID, decision.TargetID)
	if err != nil {
		return Plan{}, err
	}
	target := unitOf(board, targetID)
	weaponID := *decision.WeaponID
	weapon := weaponOf(actor, weaponID)
	if !hasENFor(actor, *weapon) {
		return Plan{}, fmt.Errorf("%w: unit %d cannot pay for the weapon %q",
			battle.ErrIllegalAction, decision.UnitID, weapon.Name)
	}
	anchor, err := destination(board, decision.UnitID, decision.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return Plan{}, err
	}
	firing := geometry.FootprintAt(actor, anchor)
	if !weapon.Reaches(geometry.Distance(firing, target.Footprint())) {
		return Plan{}, fmt.Errorf("%w: the weapon %q of unit %d does not reach unit %d",
			battle.ErrIllegalAction, weapon.Name, decision.UnitID, targetID)
	}
	joining, err := chosenSupportAttackers(board, decision.UnitID, firing, target.Footprint(),
		decision.SupportAttackerIDs)
	if err != nil {
		return Plan{}, err
	}
	bearerID, err := chosenSupportDefendWhenAttack(board, decision.UnitID, firing,
		decision.SupportDefenderID)
	if err != nil {
		return Plan{}, err
	}
	reply, err := answerOf(board, targetID, firing, decision.ResponseAttack)
	if err != nil {
		return Plan{}, err
	}
	return Plan{
		kind:     battle.ActionAttack,
		actorID:  decision.UnitID,
		anchor:   anchor,
		targetID: &targetID,
		weaponID: &weaponID,
		joining:  joining,
		bearerID: bearerID,
		answer:   reply,
	}, nil
}

func Activatable(board *state.Battle, unitID int) (*state.Unit, error) {
	unit, err := LivingUnit(board, unitID)
	if err != nil {
		return nil, err
	}
	if err := OnPhase(board, unit); err != nil {
		return nil, err
	}
	if unit.Value.Acted {
		return nil, fmt.Errorf("%w: %d", battle.ErrActed, unitID)
	}
	return unit, nil
}

// LivingUnit and OnPhase are the two gates that every command reads, so the
// shell asks them here and no package writes the refusal twice.
func LivingUnit(board *state.Battle, unitID int) (*state.Unit, error) {
	unit, err := board.UnitAt(unitID)
	if err != nil {
		return nil, err
	}
	if !unit.Alive() {
		return nil, fmt.Errorf("%w: %d", battle.ErrDestroyed, unitID)
	}
	return unit, nil
}

func OnPhase(board *state.Battle, unit *state.Unit) error {
	if unit.Faction != board.Phase {
		return fmt.Errorf("%w: the side %q does not hold the phase %q",
			battle.ErrOffPhase, unit.Faction, board.Phase)
	}
	return nil
}

func foe(board *state.Battle, actorID int, targetID *int) (int, error) {
	if targetID == nil {
		return 0, fmt.Errorf("%w: the attack of unit %d names no target",
			battle.ErrIllegalAction, actorID)
	}
	target, err := LivingUnit(board, *targetID)
	if err != nil {
		return 0, err
	}
	if target.Faction != unitOf(board, actorID).Faction.Opposing() {
		return 0, fmt.Errorf("%w: unit %d of the side %q is no foe of unit %d",
			battle.ErrIllegalAction, *targetID, target.Faction, actorID)
	}
	return *targetID, nil
}

func destination(board *state.Battle, actorID int, to *battle.Cell, permitted bool) (battle.Cell, error) {
	actor := unitOf(board, actorID)
	if to == nil {
		return actor.Value.Pos, nil
	}
	if !permitted {
		return battle.Cell{}, fmt.Errorf("%w: the action of unit %d runs before a move",
			battle.ErrIllegalMove, actorID)
	}
	if !geometry.ReachableAnchors(board, actorID)[*to] {
		return battle.Cell{}, fmt.Errorf("%w: unit %d does not reach the anchor %v",
			battle.ErrIllegalMove, actorID, *to)
	}
	return *to, nil
}

func answerOf(board *state.Battle, defenderID int, firing battle.Footprint,
	response *battle.ResponseAttack) (answer, error) {
	if response == nil {
		return answer{}, nil
	}
	out := answer{response: response}
	defender := unitOf(board, defenderID)
	if !knownStances[response.Stance] {
		return answer{}, fmt.Errorf("%w: unit %d takes the stance %q, which is not in the contract",
			battle.ErrIllegalAction, defenderID, response.Stance)
	}
	if response.Stance == battle.StanceCounter {
		counterID, fires := counterWeapon(defender, response.WeaponID, firing)
		if !fires {
			return answer{}, fmt.Errorf("%w: unit %d counters the strike with no weapon that reaches the attacker",
				battle.ErrIllegalAction, defenderID)
		}
		out.counterWeaponID = &counterID
	} else if response.WeaponID != nil {
		return answer{}, fmt.Errorf("%w: the stance %q of unit %d fires no weapon",
			battle.ErrIllegalAction, response.Stance, defenderID)
	}
	supportDefenderID, err := chosenSupportDefender(board, defenderID, defender.Footprint(),
		response.SupportDefenderID, func(*state.Unit) bool { return true })
	if err != nil {
		return answer{}, err
	}
	// A defender that defends blocks the strike for itself and leaves the
	// supportDefender nothing to take (docs/reference/battle-prep-ui.md:279, issue
	// #44). Whether the game pairs a support defender with the stand is not
	// measured; the engine permits it until a measurement lands.
	if supportDefenderID != nil && response.Stance == battle.StanceDefend {
		return answer{}, fmt.Errorf("%w: unit %d defends the strike itself and takes no support defender",
			battle.ErrIllegalAction, defenderID)
	}
	out.supportDefenderID = supportDefenderID
	if out.joining, err = chosenSupportAttackers(board, defenderID, defender.Footprint(), firing,
		response.SupportAttackerIDs); err != nil {
		return answer{}, err
	}
	return out, nil
}

func chosenSupportAttackers(board *state.Battle, supportedID int, firing, foe battle.Footprint,
	ids []int) ([]supportAttacker, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	if len(ids) > maxSupportAttackers {
		return nil, fmt.Errorf("%w: unit %d names %d support attackers, and the rules permit %d",
			battle.ErrIllegalAction, supportedID, len(ids), maxSupportAttackers)
	}
	eligible := map[int]int{}
	for _, one := range supportAttackers(board, supportedID, firing, foe) {
		eligible[one.UnitID] = one.WeaponID
	}
	out := make([]supportAttacker, 0, len(ids))
	for _, id := range ids {
		if slices.ContainsFunc(out, func(one supportAttacker) bool { return one.UnitID == id }) {
			return nil, fmt.Errorf("%w: unit %d joins the strike of unit %d two times",
				battle.ErrIllegalAction, id, supportedID)
		}
		weaponID, joins := eligible[id]
		if !joins {
			return nil, fmt.Errorf("%w: unit %d cannot join the strike of unit %d",
				battle.ErrIllegalAction, id, supportedID)
		}
		out = append(out, supportAttacker{UnitID: id, WeaponID: weaponID})
	}
	return out, nil
}

func chosenSupportDefender(board *state.Battle, coveredID int, at battle.Footprint, id *int,
	fits func(*state.Unit) bool) (*int, error) {
	if id == nil {
		return nil, nil
	}
	if slices.Contains(supportDefenders(board, coveredID, at), *id) && fits(unitOf(board, *id)) {
		return id, nil
	}
	return nil, fmt.Errorf("%w: unit %d takes no strike for unit %d",
		battle.ErrIllegalAction, *id, coveredID)
}

func chosenSupportDefendWhenAttack(board *state.Battle, actorID int, firing battle.Footprint,
	id *int) (*int, error) {
	return chosenSupportDefender(board, actorID, firing, id,
		func(other *state.Unit) bool { return other.SupportDefendWhenAttack })
}
