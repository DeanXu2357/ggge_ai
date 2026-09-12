package engagement

import (
	"fmt"
	"math/rand/v2"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Commit(board state.Battle, action battle.Action, draw *rand.Rand) (state.Values, []battle.Event, error) {
	if err := check(board, action); err != nil {
		return state.Values{}, nil, err
	}
	working := board.Values.Clone()
	return working, nil, nil
}

const maxSupportAttackers = 3

// check refuses an action the board cannot settle, and answers nothing else:
// the segments read the action for themselves.
func check(board state.Battle, action battle.Action) error {
	actor, err := Activatable(board, action.ActorID)
	if err != nil {
		return err
	}
	if action.MapAttack != nil {
		return fmt.Errorf("%w: the engine fires no map weapon, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	}
	if (action.Attack == nil) != (action.ResponseAttack == nil) {
		return fmt.Errorf("%w: an attack and its response attack travel together",
			battle.ErrIllegalAction)
	}
	if action.Attack == nil {
		_, err := destination(board, action.ActorID, action.MoveTo, true)
		return err
	}
	anchor, err := checkAttack(board, action, actor)
	if err != nil {
		return err
	}
	firing := geometry.FootprintAt(actor, anchor)
	target := unitOf(board, action.Attack.TargetID)
	dodging := action.ResponseAttack.Stance == battle.StanceDodge
	if err := checkSide(board, action.ActorID, firing, target, target.Footprint(), dodging,
		action.Attack.SupportAttackers, action.Attack.SupportDefenderID); err != nil {
		return err
	}
	if err := checkResponse(board, action, actor, firing); err != nil {
		return err
	}
	return checkSide(board, action.Attack.TargetID, target.Footprint(), actor, firing, false,
		action.ResponseAttack.SupportAttackers, action.ResponseAttack.SupportDefenderID)
}

// checkAttack answers the anchor of the actor after its move, which the
// defender side reads as the cell its strikes must reach.
func checkAttack(board state.Battle, action battle.Action, actor state.Unit) (battle.Cell, error) {
	attack := action.Attack
	weapon, err := actor.WeaponAt(attack.WeaponID)
	if err != nil {
		return battle.Cell{}, err
	}
	targetID, err := foe(board, action.ActorID, attack.TargetID)
	if err != nil {
		return battle.Cell{}, err
	}
	anchor, err := destination(board, action.ActorID, action.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return battle.Cell{}, err
	}
	target := unitOf(board, targetID)
	firing := geometry.FootprintAt(actor, anchor)
	if err := canFire(actor, action.ActorID, weapon, firing, target.Footprint()); err != nil {
		return battle.Cell{}, err
	}
	dodging := action.ResponseAttack.Stance == battle.StanceDodge
	if err := checkStated(actor, target, weapon, dodging, attack.Stated); err != nil {
		return battle.Cell{}, err
	}
	return anchor, nil
}

func checkResponse(board state.Battle, action battle.Action, actor state.Unit, firing battle.Footprint) error {
	response := action.ResponseAttack
	targetID := action.Attack.TargetID
	target := unitOf(board, targetID)
	switch response.Stance {
	case battle.StanceCounter:
		if response.WeaponID == nil {
			return fmt.Errorf("%w: the counter of unit %d names no weapon",
				battle.ErrIllegalAction, targetID)
		}
		weapon, err := target.WeaponAt(*response.WeaponID)
		if err != nil {
			return err
		}
		if err := canFire(target, targetID, weapon, target.Footprint(), firing); err != nil {
			return err
		}
		return checkStated(target, actor, weapon, false, response.Stated)
	case battle.StanceDodge, battle.StanceDefend, battle.StanceNone:
		if response.WeaponID != nil {
			return fmt.Errorf("%w: the stance %q of unit %d fires no weapon",
				battle.ErrIllegalAction, response.Stance, targetID)
		}
		if response.Stance == battle.StanceDefend && response.SupportDefenderID != nil {
			return fmt.Errorf("%w: unit %d defends and names a support defender",
				battle.ErrIllegalAction, targetID)
		}
		return nil
	}
	return fmt.Errorf("%w: the stance %q is not in the contract",
		battle.ErrIllegalAction, response.Stance)
}

// checkSide checks the support units of one side: the supported unit stands
// on 'at' after its move, and every support attack aims at 'foe' on 'foeAt'.
func checkSide(board state.Battle, supportedID int, at battle.Footprint, foe state.Unit, foeAt battle.Footprint,
	dodging bool, supporters []battle.SupportAttacker, guardID *int) error {
	if len(supporters) > maxSupportAttackers {
		return fmt.Errorf("%w: %d support attackers exceed the cap of %d",
			battle.ErrIllegalAction, len(supporters), maxSupportAttackers)
	}
	named := map[int]bool{}
	for _, supporter := range supporters {
		if named[supporter.UnitID] {
			return fmt.Errorf("%w: unit %d is named two times on one side",
				battle.ErrIllegalAction, supporter.UnitID)
		}
		named[supporter.UnitID] = true
		if err := checkSupporter(board, supportedID, at, foe, foeAt, dodging, supporter); err != nil {
			return err
		}
	}
	if guardID == nil {
		return nil
	}
	if named[*guardID] {
		return fmt.Errorf("%w: unit %d is named two times on one side",
			battle.ErrIllegalAction, *guardID)
	}
	guard, err := supportUnit(board, supportedID, *guardID, at)
	if err != nil {
		return err
	}
	if guard.Value.SupportDefendCharges <= 0 {
		return fmt.Errorf("%w: unit %d holds no support defend charge",
			battle.ErrIllegalAction, *guardID)
	}
	return nil
}

func checkSupporter(board state.Battle, supportedID int, at battle.Footprint, foe state.Unit, foeAt battle.Footprint,
	dodging bool, supporter battle.SupportAttacker) error {
	unit, err := supportUnit(board, supportedID, supporter.UnitID, at)
	if err != nil {
		return err
	}
	if unit.Value.SupportAttackCharges <= 0 {
		return fmt.Errorf("%w: unit %d holds no support attack charge",
			battle.ErrIllegalAction, supporter.UnitID)
	}
	weapon, err := unit.WeaponAt(supporter.WeaponID)
	if err != nil {
		return err
	}
	if err := canFire(unit, supporter.UnitID, weapon, unit.Footprint(), foeAt); err != nil {
		return err
	}
	return checkStated(unit, foe, weapon, dodging, supporter.Stated)
}

// supportUnit answers a living unit of the side of the supported unit that
// stands within its own move range of the cell the supported unit holds.
func supportUnit(board state.Battle, supportedID, unitID int, at battle.Footprint) (state.Unit, error) {
	unit, err := LivingUnit(board, unitID)
	if err != nil {
		return state.Unit{}, err
	}
	if unit.Faction != unitOf(board, supportedID).Faction {
		return state.Unit{}, fmt.Errorf("%w: unit %d is not of the side of unit %d",
			battle.ErrIllegalAction, unitID, supportedID)
	}
	if unitID == supportedID || geometry.Distance(unit.Footprint(), at) > unit.Mech.MoveRange {
		return state.Unit{}, fmt.Errorf("%w: unit %d is out of support reach of unit %d",
			battle.ErrIllegalAction, unitID, supportedID)
	}
	return unit, nil
}

func canFire(shooter state.Unit, shooterID int, weapon *def.Weapon, from, at battle.Footprint) error {
	if !hasENFor(shooter, *weapon) {
		return fmt.Errorf("%w: unit %d cannot pay for the weapon %q",
			battle.ErrIllegalAction, shooterID, weapon.Name)
	}
	if !weapon.Reaches(geometry.Distance(from, at)) {
		return fmt.Errorf("%w: the weapon %q of unit %d does not reach",
			battle.ErrIllegalAction, weapon.Name, shooterID)
	}
	return nil
}

// No rule computes a critical rate, so every stated critical is a behavior
// the rates give no chance of.
func checkStated(shooter, aimed state.Unit, weapon *def.Weapon, dodging bool, stated *battle.Stated) error {
	if stated == nil {
		return nil
	}
	if stated.Crit {
		return fmt.Errorf("%w: the weapon %q states a critical at a critical rate of 0",
			battle.ErrIllegalAction, weapon.Name)
	}
	rate := strikeHitProbability(shooter, aimed, weapon, dodging)
	if stated.Hit && rate <= 0 {
		return fmt.Errorf("%w: the weapon %q states a hit at a hit rate of 0",
			battle.ErrIllegalAction, weapon.Name)
	}
	if !stated.Hit && rate >= 1 {
		return fmt.Errorf("%w: the weapon %q states a miss at a hit rate of 1",
			battle.ErrIllegalAction, weapon.Name)
	}
	return nil
}
