package system

import (
	"fmt"
	"math/rand/v2"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Commit(board state.Battle, action battle.Action, draw *rand.Rand) (state.Values, []battle.Event, error) {
	if outcome := Outcome(board); outcome != battle.OutcomeOngoing {
		return state.Values{}, nil, fmt.Errorf("%w: %s", battle.ErrBattleOver, outcome)
	}

	schedule, err := scheduleAct(board, action)
	if err != nil {
		return state.Values{}, nil, err
	}

	if err := checkStatements(board, schedule.strikes); err != nil {
		return state.Values{}, nil, err
	}

	working := board.Values.Clone()
	view := state.Battle{Content: board.Content, Values: &working}

	var events []battle.Event
	if schedule.from != schedule.to {
		unitOf(view, schedule.actorID).Value.Pos = schedule.to
		events = append(events, battle.MoveEvent{Kind: battle.EventMove,
			ActorID: schedule.actorID, From: schedule.from, To: schedule.to})
	}
	x := exchange{board: view, draw: draw, actorID: schedule.actorID, paid: map[int]bool{}}
	for _, s := range schedule.strikes {
		events = append(events, x.fire(s))
	}

	events = append(events, endActivation(view, schedule.actorID, x.killed))
	if Outcome(view) == battle.OutcomeOngoing {
		for _, rotation := range rotate(view) {
			events = append(events, rotation)
		}
	}
	return working, events, nil
}

func endActivation(board state.Battle, actorID int, killed bool) battle.ActivationEndEvent {
	actor := unitOf(board, actorID)
	var led ledger
	if killed && actor.Alive() && actor.Value.ChanceSteps > 0 {
		led.unit(actorID).ChanceSteps = change(&actor.Value.ChanceSteps, actor.Value.ChanceSteps-1)
	} else {
		led.unit(actorID).Acted = change(&actor.Value.Acted, true)
	}
	return battle.ActivationEndEvent{Kind: battle.EventActivationEnd, ActorID: actorID, Effects: led.list()}
}

// A statement pins one behavior of a strike so that a forecast settles the
// exchange under that behavior. It is a device of the simulation, not a rule
// of the game, so the check runs between the schedule and the exchange and
// reads the state before the first strike.
func checkStatements(board state.Battle, strikes []strike) error {
	for _, s := range strikes {
		if s.stated == nil {
			continue
		}
		if err := checkStated(unitOf(board, s.shooterID), unitOf(board, s.aimedID),
			s.weapon, s.dodging, s.stated); err != nil {
			return err
		}
	}
	return nil
}

func checkStated(shooter, aimed unit, weapon *def.Weapon, dodging bool, stated *battle.Stated) error {
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
