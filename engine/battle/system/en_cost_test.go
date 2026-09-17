package system

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func supportENCostLine() ability.Line {
	return lines.WeaponENCostPercentOnSupportWithMechType{MechType: def.MechTypeSupport, Percent: -20}
}

// The squad with the supporter of the mech type 3 (支援型) and the line.
func scenarioSquadWithENCostLine() state.Battle {
	b := scenarioSquad()
	b.Content.Units[supporterID].Mech.Type = def.MechTypeSupport
	b.Values.Units[supporterID].SetAbilities([]ability.Line{supportENCostLine()})
	return b
}

// The EN a unit spent in the strikes of the events.
func enSpent(t *testing.T, events []battle.Event, unitID int) int {
	t.Helper()
	spent := 0
	for _, s := range strikes(events) {
		for _, effect := range s.Effects {
			if effect.UnitID == unitID && effect.EN != nil {
				spent += effect.EN.From - effect.EN.To
			}
		}
	}
	return spent
}

func supportedAttack() battle.Action {
	return battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit(),
			SupportAttackers: []battle.SupportAttacker{{UnitID: supporterID, WeaponID: 0, Stated: hit()}}},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone}}
}

// "When piloting units with specified types and executing Support
// Attack/Counter, reduce own weapon EN consumption by 20%": the support
// strike of the supporter with the line spends the discounted cost, and the
// same line on the actor or on a supporter of another type spends the full
// cost.
func TestASupportENCostLineDiscountsTheStrikeOfTheSupporterAlone(t *testing.T) {
	_, events := accepted(t, scenarioSquadWithENCostLine(), supportedAttack())
	assert.Equal(t, 8, enSpent(t, events, supporterID), "the supporter with the line")

	_, events = accepted(t, scenarioSquad(), supportedAttack())
	assert.Equal(t, 10, enSpent(t, events, supporterID), "the supporter without the line")

	wrongType := scenarioSquadWithENCostLine()
	wrongType.Content.Units[supporterID].Mech.Type = def.MechTypeDurable
	_, events = accepted(t, wrongType, supportedAttack())
	assert.Equal(t, 10, enSpent(t, events, supporterID), "a supporter of another type")

	asActor := scenarioSquad()
	asActor.Content.Units[actorID].Mech.Type = def.MechTypeSupport
	asActor.Values.Units[actorID].SetAbilities([]ability.Line{supportENCostLine()})
	_, events = accepted(t, asActor, supportedAttack())
	assert.Equal(t, 10, enSpent(t, events, actorID), "the actor with the line")
}

// The menu and the schedule read the same cost as the write: a supporter
// that can pay the discounted cost and not the full one is offered and
// accepted with the line, and neither without it.
func TestTheDiscountedCostIsTheCostTheMenuAndTheScheduleRead(t *testing.T) {
	decision := battle.Decision{UnitID: actorID, Kind: battle.ActionAttack, WeaponID: idOf(0), TargetID: idOf(targetID)}

	lined := scenarioSquadWithENCostLine()
	lined.Values.Units[supporterID].EN = 8
	menu, err := Menu(lined, decision, targetID)
	require.NoError(t, err)
	require.Len(t, menu.Attacker.SupportAttackers, 1, "the menu offers the supporter with the line")
	assert.Equal(t, supporterID, menu.Attacker.SupportAttackers[0].UnitID)
	_, events := accepted(t, lined, supportedAttack())
	assert.Equal(t, 8, enSpent(t, events, supporterID))

	plain := scenarioSquad()
	plain.Values.Units[supporterID].EN = 8
	menu, err = Menu(plain, decision, targetID)
	require.NoError(t, err)
	assert.Empty(t, menu.Attacker.SupportAttackers, "the menu omits the supporter without the line")
	refused(t, plain, supportedAttack(), battle.ErrIllegalAction)
}
