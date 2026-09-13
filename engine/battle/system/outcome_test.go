package system

import (
	"errors"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func TestOutcomeReadsTheLivingUnitsOfEachSide(t *testing.T) {
	wreck := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	wreck.HP = 0
	fallen := fighter(battle.FactionAlly, battle.Cell{0, 0})
	fallen.HP = 0
	for name, tc := range map[string]struct {
		units []battle.Unit
		want  battle.Outcome
	}{
		"both sides stand":  {[]battle.Unit{fighter(battle.FactionAlly, battle.Cell{0, 0}), fighter(battle.FactionEnemy, battle.Cell{3, 0})}, battle.OutcomeOngoing},
		"the enemy is gone": {[]battle.Unit{fighter(battle.FactionAlly, battle.Cell{0, 0}), wreck}, battle.OutcomeVictory},
		"the ally is gone":  {[]battle.Unit{fallen, fighter(battle.FactionEnemy, battle.Cell{3, 0})}, battle.OutcomeDefeat},
	} {
		t.Run(name, func(t *testing.T) {
			if got := Outcome(board(tc.units...)); got != tc.want {
				t.Fatalf("outcome: %s, want %s", got, tc.want)
			}
		})
	}
}

func TestCommitRefusesAnActOnASettledBattle(t *testing.T) {
	wreck := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	wreck.HP = 0
	b := board(fighter(battle.FactionAlly, battle.Cell{0, 0}), wreck)

	refused(t, b, battle.Action{ActorID: actorID}, battle.ErrBattleOver)
}

// The last enemy falls to the main strike: the activation ends, and no
// phase rotates on a settled battle.
func TestCommitDoesNotRotateAfterTheBattleSettles(t *testing.T) {
	b := shootout()
	b.Values.Units[targetID].HP = 1
	values, events := accepted(t, b, battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit()}, ResponseAttack: none()})

	expectKinds(t, events, battle.EventStrike, battle.EventActivationEnd)
	if values.Phase != battle.FactionAlly || values.Units[targetID].HP != 0 {
		t.Fatalf("phase %s, target hp %d", values.Phase, values.Units[targetID].HP)
	}
}

func TestMenuRefusesAQuestionOnASettledBattle(t *testing.T) {
	b := duel()
	b.Values.Units[duelDefenderID].HP = 0
	b.Values.Units[duelHelperID].HP = 0

	_, err := Menu(b, strikeAction(battle.Cell{1, 0}, 0), duelDefenderID)

	if !errors.Is(err, battle.ErrBattleOver) {
		t.Fatalf("error: %v", err)
	}
}
