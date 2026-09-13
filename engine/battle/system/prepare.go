package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// A plan carries the strike that the question 'response_attacks' asks about:
// the actor, its anchor after the move, its weapon and its target. The act
// reads 'parse' and not this.
type plan struct {
	kind     battle.ActionKind
	actorID  int
	anchor   battle.Cell
	targetID *int
	weaponID *int
}

func prepare(board state.Battle, decision battle.Decision) (plan, error) {
	actor, err := Activatable(board, decision.UnitID)
	if err != nil {
		return plan{}, err
	}
	if err := checkIDs(board, decision); err != nil {
		return plan{}, err
	}
	switch decision.Kind {
	case battle.ActionAttack:
		return prepareAttack(board, decision, actor)
	case battle.ActionMapAttack:
		return plan{}, fmt.Errorf("%w: the engine resolves no map attack, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	case battle.ActionReposition, battle.ActionStandby:
		anchor, err := destination(board, decision.UnitID, decision.MoveTo, true)
		if err != nil {
			return plan{}, err
		}
		return plan{kind: decision.Kind, actorID: decision.UnitID, anchor: anchor}, nil
	}
	return plan{}, fmt.Errorf("%w: the kind %q is no action of a unit",
		battle.ErrIllegalAction, decision.Kind)
}

// checkIDs bounds-checks every id that the wire carries, one time, before the
// first write. Past this gate an id names a thing of the board.
func checkIDs(board state.Battle, decision battle.Decision) error {
	actor, err := board.UnitAt(decision.UnitID)
	if err != nil {
		return err
	}
	if decision.TargetID != nil {
		if _, err := board.UnitAt(*decision.TargetID); err != nil {
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
	return checkArmament(decision)
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

func prepareAttack(board state.Battle, decision battle.Decision, actor state.Unit) (plan, error) {
	if decision.MapWeaponID != nil {
		return plan{}, fmt.Errorf("%w: the engine fires no map weapon, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	}
	if decision.TargetID == nil {
		return plan{}, fmt.Errorf("%w: the attack of unit %d names no target",
			battle.ErrIllegalAction, decision.UnitID)
	}
	targetID, err := foe(board, decision.UnitID, *decision.TargetID)
	if err != nil {
		return plan{}, err
	}
	target := unitOf(board, targetID)
	weaponID := *decision.WeaponID
	weapon := weaponOf(actor, weaponID)
	if !hasENFor(actor, *weapon) {
		return plan{}, fmt.Errorf("%w: unit %d cannot pay for the weapon %q",
			battle.ErrIllegalAction, decision.UnitID, weapon.Name)
	}
	anchor, err := destination(board, decision.UnitID, decision.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return plan{}, err
	}
	firing := geometry.FootprintAt(actor, anchor)
	if !weapon.Reaches(geometry.Distance(firing, target.Footprint())) {
		return plan{}, fmt.Errorf("%w: the weapon %q of unit %d does not reach unit %d",
			battle.ErrIllegalAction, weapon.Name, decision.UnitID, targetID)
	}
	return plan{
		kind:     battle.ActionAttack,
		actorID:  decision.UnitID,
		anchor:   anchor,
		targetID: &targetID,
		weaponID: &weaponID,
	}, nil
}

func foe(board state.Battle, actorID int, targetID int) (int, error) {
	target, err := LivingUnit(board, targetID)
	if err != nil {
		return 0, err
	}
	if target.Faction != unitOf(board, actorID).Faction.Opposing() {
		return 0, fmt.Errorf("%w: unit %d of the side %q is no foe of unit %d",
			battle.ErrIllegalAction, targetID, target.Faction, actorID)
	}
	return targetID, nil
}

func destination(board state.Battle, actorID int, to *battle.Cell, permitted bool) (battle.Cell, error) {
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
