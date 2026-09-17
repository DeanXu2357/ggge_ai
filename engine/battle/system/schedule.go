package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const maxSupportAttackers = 3

// No value of the working column enters a strike: the values change while
// the exchange runs.
type strike struct {
	segment   battle.Segment
	ownerID   int // the actor for the attacker side, the target for the defender side
	shooterID int
	weaponID  int
	weapon    *def.Weapon
	aimedID   int
	dodging   bool // the aimed unit dodges; the hit rate reads it whoever is struck
	struckID  int
	stance    battle.Stance // the stance of the struck unit; a support defender defends
	stated    *battle.Stated
}

type actSchedule struct {
	actorID int
	from    battle.Cell
	to      battle.Cell
	cast    cast
	strikes []strike
}

func scheduleAct(board state.Battle, action battle.Action) (actSchedule, error) {
	actor, err := activatable(board, action.ActorID)
	if err != nil {
		return actSchedule{}, err
	}

	if action.MapAttack != nil {
		return actSchedule{}, fmt.Errorf("%w: the engine fires no map weapon, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	}

	if (action.Attack == nil) != (action.ResponseAttack == nil) {
		return actSchedule{}, fmt.Errorf("%w: an attack and its response attack travel together",
			battle.ErrIllegalAction)
	}

	if action.Attack == nil {
		to, err := destination(board, action.ActorID, action.MoveTo, true)
		if err != nil {
			return actSchedule{}, err
		}
		return actSchedule{actorID: action.ActorID, from: actor.Value.Pos, to: to}, nil
	}

	attack, response := action.Attack, action.ResponseAttack
	weapon, err := actor.WeaponAt(attack.WeaponID)
	if err != nil {
		return actSchedule{}, err
	}

	targetID, err := foe(board, action.ActorID, attack.TargetID)
	if err != nil {
		return actSchedule{}, err
	}

	to, err := destination(board, action.ActorID, action.MoveTo, weapon.UsableAfterMove)
	if err != nil {
		return actSchedule{}, err
	}

	target := unitOf(board, targetID)
	firing := actor.footprintAt(to)
	standing := target.Footprint()
	who := cast{actorID: action.ActorID, targetID: targetID}

	main := strike{segment: battle.SegmentMain, ownerID: action.ActorID,
		shooterID: action.ActorID, weaponID: attack.WeaponID, weapon: weapon,
		aimedID: targetID, dodging: response.Stance == battle.StanceDodge, stated: attack.Stated}
	main.struckID, main.stance = struckBy(response.SupportDefenderID, targetID, response.Stance)
	if err := canFire(actor, who.part(actor.id), weapon, geometry.Distance(firing, standing)); err != nil {
		return actSchedule{}, err
	}
	attackerSupport, err := supportStrikes(board, who, main.as(battle.SegmentAttackerSupport),
		firing, standing, attack.SupportAttackers, attack.SupportDefenderID)
	if err != nil {
		return actSchedule{}, err
	}
	counter, err := counterOf(board, who, action, actor, target, firing)
	if err != nil {
		return actSchedule{}, err
	}
	reply := strike{segment: battle.SegmentDefenderSupport, ownerID: targetID, aimedID: action.ActorID}
	reply.struckID, reply.stance = struckBy(attack.SupportDefenderID, action.ActorID, battle.StanceNone)
	defenderSupport, err := supportStrikes(board, who, reply,
		standing, firing, response.SupportAttackers, response.SupportDefenderID)
	if err != nil {
		return actSchedule{}, err
	}

	schedule := actSchedule{actorID: action.ActorID, from: actor.Value.Pos, to: to, cast: who}
	schedule.strikes = append(schedule.strikes, attackerSupport...)
	schedule.strikes = append(schedule.strikes, main)
	schedule.strikes = append(schedule.strikes, defenderSupport...)
	if counter != nil {
		schedule.strikes = append(schedule.strikes, *counter)
	}
	return schedule, nil
}

func (s strike) as(segment battle.Segment) strike {
	s.segment = segment
	return s
}

func struckBy(guardID *int, aimedID int, stance battle.Stance) (int, battle.Stance) {
	if guardID != nil {
		return *guardID, battle.StanceDefend
	}
	return aimedID, stance
}

func counterOf(board state.Battle, who cast, action battle.Action, actor, target unit,
	firing battle.Footprint) (*strike, error) {
	response := action.ResponseAttack
	targetID := action.Attack.TargetID
	switch response.Stance {
	case battle.StanceCounter:
		if response.WeaponID == nil {
			return nil, fmt.Errorf("%w: the counter of unit %d names no weapon",
				battle.ErrIllegalAction, targetID)
		}
		weapon, err := target.WeaponAt(*response.WeaponID)
		if err != nil {
			return nil, err
		}
		if err := canFire(target, who.part(target.id), weapon, geometry.Distance(target.Footprint(), firing)); err != nil {
			return nil, err
		}
		counter := strike{segment: battle.SegmentCounter, ownerID: targetID,
			shooterID: targetID, weaponID: *response.WeaponID, weapon: weapon,
			aimedID: action.ActorID, stated: response.Stated}
		counter.struckID, counter.stance = struckBy(action.Attack.SupportDefenderID, action.ActorID, battle.StanceNone)
		return &counter, nil
	case battle.StanceDodge, battle.StanceDefend, battle.StanceNone:
		if response.WeaponID != nil {
			return nil, fmt.Errorf("%w: the stance %q of unit %d fires no weapon",
				battle.ErrIllegalAction, response.Stance, targetID)
		}
		if response.Stance == battle.StanceDefend && response.SupportDefenderID != nil {
			return nil, fmt.Errorf("%w: unit %d defends and names a support defender",
				battle.ErrIllegalAction, targetID)
		}
		return nil, nil
	}
	return nil, fmt.Errorf("%w: the stance %q is not in the contract",
		battle.ErrIllegalAction, response.Stance)
}

func supportStrikes(board state.Battle, who cast, base strike, at, foeAt battle.Footprint,
	supporters []battle.SupportAttacker, guardID *int) ([]strike, error) {
	if len(supporters) > maxSupportAttackers {
		return nil, fmt.Errorf("%w: %d support attackers exceed the cap of %d",
			battle.ErrIllegalAction, len(supporters), maxSupportAttackers)
	}
	named := map[int]bool{}
	out := make([]strike, 0, len(supporters))
	for _, supporter := range supporters {
		if named[supporter.UnitID] {
			return nil, fmt.Errorf("%w: unit %d is named two times on one side",
				battle.ErrIllegalAction, supporter.UnitID)
		}
		named[supporter.UnitID] = true
		unit, err := supportUnit(board, base.ownerID, supporter.UnitID, at)
		if err != nil {
			return nil, err
		}
		if unit.Value.SupportAttackCharges <= 0 {
			return nil, fmt.Errorf("%w: unit %d holds no support attack charge",
				battle.ErrIllegalAction, supporter.UnitID)
		}
		weapon, err := unit.WeaponAt(supporter.WeaponID)
		if err != nil {
			return nil, err
		}
		if err := canFire(unit, who.part(unit.id), weapon, geometry.Distance(unit.Footprint(), foeAt)); err != nil {
			return nil, err
		}
		support := base
		support.shooterID, support.weaponID, support.weapon, support.stated =
			supporter.UnitID, supporter.WeaponID, weapon, supporter.Stated
		out = append(out, support)
	}
	if guardID == nil {
		return out, nil
	}
	if named[*guardID] {
		return nil, fmt.Errorf("%w: unit %d is named two times on one side",
			battle.ErrIllegalAction, *guardID)
	}
	guard, err := supportUnit(board, base.ownerID, *guardID, at)
	if err != nil {
		return nil, err
	}
	if guard.Value.SupportDefendCharges <= 0 {
		return nil, fmt.Errorf("%w: unit %d holds no support defend charge",
			battle.ErrIllegalAction, *guardID)
	}
	return out, nil
}

func supportUnit(board state.Battle, supportedID, unitID int, at battle.Footprint) (unit, error) {
	u, err := livingUnit(board, unitID)
	if err != nil {
		return unit{}, err
	}
	if u.Faction != unitOf(board, supportedID).Faction {
		return unit{}, fmt.Errorf("%w: unit %d is not of the side of unit %d",
			battle.ErrIllegalAction, unitID, supportedID)
	}
	if unitID == supportedID || geometry.Distance(u.Footprint(), at) > u.Value.MoveRange {
		return unit{}, fmt.Errorf("%w: unit %d is out of support reach of unit %d",
			battle.ErrIllegalAction, unitID, supportedID)
	}
	return u, nil
}
