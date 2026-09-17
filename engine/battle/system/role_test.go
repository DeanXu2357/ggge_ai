package system

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const guardID = 2

// The duel with a guard of the target at (3,1): one support defend charge,
// a move range that reaches the target, the mech type 2 (耐久型).
func scenarioCover() state.Battle {
	b := scenarioDuel()
	units := state.Battle{Content: b.Content, Values: b.Values}.ToContract().Units
	guard := battle.Unit{Faction: battle.FactionEnemy, Pos: battle.Cell{3, 1}, Size: battle.Cell{1, 1},
		HP: 99000, EN: 140, MoveRange: 2, SupportDefendCharges: 1, SupportDefendChargesMax: 1,
		Pilot: battle.Pilot{Ranged: 220, Melee: 220, Awaken: 220, Defense: 190, Reaction: 205, SP: 15},
		Mech:  battle.Mech{HP: 99000, EN: 140, Attack: 4200, Defense: 3900, Mobility: 310, MoveRange: 2}}
	bounds := b.Content.Bounds
	content, values := assembled(battle.BattleState{
		Bounds: &bounds, Phase: battle.FactionAlly, Turn: 1, Units: append(units, guard)})
	content.Units[guardID].Mech.Type = battle.MechTypeDurable
	return state.Battle{Content: &content, Values: &values}
}

// The actor fires at the target and the guard covers; the main strike
// lands on the guard. Its damage is answered.
func mainDamageOnTheGuard(t *testing.T, b state.Battle) int {
	t.Helper()
	_, events := accepted(t, b, battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit()},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone, SupportDefenderID: idOf(guardID)}})
	got := strikes(events)
	require.Len(t, got, 1)
	require.Equal(t, guardID, got[0].StruckID)
	return got[0].Damage
}

// A support-defense line counts for the unit that covers, and for no one
// else: the guard with the line takes the strike of a guard whose defense is
// scaled; the target with the same line, struck as the target, meets no
// line; a guard of another mech type meets no typed line.
func TestASupportDefenseLineCountsForTheUnitThatCovers(t *testing.T) {
	typed := lines.MechDefensePercentOnSupportDefenseWithMechType{MechType: battle.MechTypeDurable, Percent: 20}
	untyped := lines.MechDefensePercentOnSupportDefense{Percent: 20}

	scaledGuard := scenarioCover()
	scaledGuard.Content.Units[guardID].Mech.Defense = 4680 // 3900 + 20%
	want := mainDamageOnTheGuard(t, scaledGuard)
	plain := mainDamageOnTheGuard(t, scenarioCover())

	for name, line := range map[string]ability.Line{"typed": typed, "untyped": untyped} {
		t.Run(name, func(t *testing.T) {
			lined := scenarioCover()
			lined.Values.Units[guardID].SetAbilities(nil, []ability.Line{line})
			assert.Equal(t, want, mainDamageOnTheGuard(t, lined), "the guard with the line")
		})
	}

	onTarget := scenarioDuel()
	onTarget.Values.Units[targetID].SetAbilities(nil, []ability.Line{untyped})
	assert.Equal(t, resolveDuel(t, scenarioDuel()).main, resolveDuel(t, onTarget).main,
		"the target struck as the target meets no support-defense line")

	wrongType := scenarioCover()
	wrongType.Content.Units[guardID].Mech.Type = battle.MechTypeSupport
	wrongType.Values.Units[guardID].SetAbilities(nil, []ability.Line{typed})
	assert.Equal(t, plain, mainDamageOnTheGuard(t, wrongType), "a guard of another type meets no typed line")
}

// The forecast of a support defender reads the line, because the game shows
// the damage the unit that covers would take.
func TestTheForecastOfASupportDefenderReadsItsLine(t *testing.T) {
	lined := scenarioCover()
	lined.Values.Units[guardID].SetAbilities(nil, []ability.Line{lines.MechDefensePercentOnSupportDefense{Percent: 20}})
	actor, guard := unitOf(lined, actorID), unitOf(lined, guardID)

	forecast := duelExchange(lined).supportDefenderForecast(actor, guard, &actor.Mech.Weapons[0])

	assert.Equal(t, mainDamageOnTheGuard(t, lined), *forecast.Damage)
}

// A support-attack line counts for a supporter of either side and not for
// the owner of a strike: the supporter with the line fires the support
// strike of a supporter whose attack is scaled; the same unit as the actor
// fires a plain main strike.
func TestASupportAttackLineCountsForTheSupporterAndNotForTheOwner(t *testing.T) {
	line := lines.MechAttackPercentOnSupportWithMechType{MechType: battle.MechTypeSupport, Percent: 25}
	supported := func(withLine bool, scaled bool) int {
		b := scenarioSquad()
		b.Content.Units[supporterID].Mech.Type = battle.MechTypeSupport
		if withLine {
			b.Values.Units[supporterID].SetAbilities(nil, []ability.Line{line})
		}
		if scaled {
			b.Content.Units[supporterID].Mech.Attack = 5250 // 4200 + 25%
		}
		_, events := accepted(t, b, battle.Action{ActorID: actorID,
			Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit(),
				SupportAttackers: []battle.SupportAttacker{{UnitID: supporterID, WeaponID: 0, Stated: hit()}}},
			ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone}})
		got := strikes(events)
		require.Equal(t, battle.SegmentAttackerSupport, got[0].Segment)
		return got[0].Damage
	}
	assert.Equal(t, supported(false, true), supported(true, false), "the support strike reads the line")
	assert.NotEqual(t, supported(false, false), supported(true, false), "the line changes the support strike")

	asActor := scenarioDuel()
	asActor.Content.Units[actorID].Mech.Type = battle.MechTypeSupport
	asActor.Values.Units[actorID].SetAbilities(nil, []ability.Line{line})
	assert.Equal(t, resolveDuel(t, scenarioDuel()), resolveDuel(t, asActor), "the owner of a strike meets no support line")
}

// The supporter of the defender is a support counter, which the line names
// with the support attack.
func TestASupportAttackLineCountsForTheSupportCounter(t *testing.T) {
	line := lines.MechAttackPercentOnSupportWithMechType{MechType: battle.MechTypeSupport, Percent: 25}
	counterSupport := func(withLine, scaled bool) int {
		b := scenarioSquad()
		b.Content.Units[supporterID].Faction = battle.FactionEnemy
		b.Content.Units[supporterID].Mech.Type = battle.MechTypeSupport
		b.Values.Units[supporterID].Pos = battle.Cell{3, 1}
		if withLine {
			b.Values.Units[supporterID].SetAbilities(nil, []ability.Line{line})
		}
		if scaled {
			b.Content.Units[supporterID].Mech.Attack = 5250
		}
		_, events := accepted(t, b, battle.Action{ActorID: actorID,
			Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit()},
			ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone,
				SupportAttackers: []battle.SupportAttacker{{UnitID: supporterID, WeaponID: 0, Stated: hit()}}}})
		got := strikes(events)
		require.Len(t, got, 2)
		require.Equal(t, battle.SegmentDefenderSupport, got[1].Segment)
		return got[1].Damage
	}
	assert.Equal(t, counterSupport(false, true), counterSupport(true, false))
}
