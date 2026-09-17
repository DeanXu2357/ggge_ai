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

// The duel with a supporter of the actor at (0,1): a long rifle of reach 5,
// one support attack charge, and a move range that reaches the actor.
func scenarioSquad() state.Battle {
	b := scenarioDuel()
	rifle := battle.Weapon{Name: "long rifle", Power: 1800, RangeMin: 1, RangeMax: 5,
		ENCost: 10, Accuracy: 5, UsableAfterMove: true}
	supporter := battle.Unit{Faction: battle.FactionAlly, Pos: battle.Cell{0, 1}, Size: battle.Cell{1, 1},
		HP: 99000, MaxHP: 99000, EN: 140, ENMax: 140, SupportAttackCharges: 1, SupportAttackChargesMax: 1,
		Pilot: battle.Pilot{Ranged: 220, Melee: 220, Awaken: 220, Defense: 190, Reaction: 205},
		Mech:  battle.Mech{Attack: 4200, Defense: 3900, Mobility: 310, MoveRange: 2, Weapons: []battle.Weapon{rifle}}}
	bounds := b.Content.Bounds
	units := []battle.Unit{}
	for id := range b.Content.Units {
		units = append(units, state.Battle{Content: b.Content, Values: b.Values}.ToContract().Units[id])
	}
	content, values := assembled(battle.BattleState{
		Bounds: &bounds, Phase: battle.FactionAlly, Turn: 1, Units: append(units, supporter)})
	return state.Battle{Content: &content, Values: &values}
}

const supporterID = 2

// The actor fires with the supporter, the supporter's strike is stated, the
// main strike lands, the target does not counter. The damage of the main
// strike is answered.
func mainDamageAfterSupport(t *testing.T, b state.Battle, supportLands bool) int {
	t.Helper()
	_, events := accepted(t, b, battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit(),
			SupportAttackers: []battle.SupportAttacker{{UnitID: supporterID, WeaponID: 0, Stated: &battle.Stated{Hit: supportLands}}}},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone}})
	got := strikes(events)
	require.Len(t, got, 2)
	require.Equal(t, battle.SegmentAttackerSupport, got[0].Segment)
	require.Equal(t, battle.SegmentMain, got[1].Segment)
	require.Equal(t, supportLands, got[0].Landed)
	return got[1].Damage
}

// "When HP is full, increase DEF by 20%": the main strike reads the HP of
// its moment. A support attack that lands first takes the target off full
// HP, and the main strike meets no bonus; a support attack that misses
// leaves the bonus in place.
func TestAFullHPDefenseLineIsReadAtEachStrikeOfTheExchange(t *testing.T) {
	withLine := func() state.Battle {
		b := scenarioSquad()
		b.Values.Units[targetID].SetAbilities([]ability.Line{lines.MechDefensePercentAtHPRateAtLeast{Threshold: 100, Percent: 20}}, nil)
		return b
	}
	scaledDefense := func() state.Battle {
		b := scenarioSquad()
		b.Content.Units[targetID].Mech.Defense = 4680 // 3900 + 20%
		return b
	}

	assert.Equal(t, mainDamageAfterSupport(t, scenarioSquad(), true), mainDamageAfterSupport(t, withLine(), true),
		"after a support hit the target is not at full HP: the main strike meets no bonus")
	assert.Equal(t, mainDamageAfterSupport(t, scaledDefense(), false), mainDamageAfterSupport(t, withLine(), false),
		"after a support miss the target is at full HP: the main strike meets the scaled defense")
}

// "When HP is 25% or below, increase own ATK by 25%": the threshold counts,
// one HP above it does not.
func TestALowHPAttackLineHoldsAtTheThresholdAndNotAbove(t *testing.T) {
	line := lines.MechAttackPercentAtHPRateAtMost{Threshold: 25, Percent: 25}
	at := func(hp int, withLine bool) exchangeDamage {
		b := scenarioDuel()
		b.Content.Units[actorID].MaxHP = 100000
		b.Values.Units[actorID].HP = hp
		if withLine {
			b.Values.Units[actorID].SetAbilities([]ability.Line{line}, nil)
		}
		return resolveDuel(t, b)
	}
	scaled := func(hp int) exchangeDamage {
		b := scenarioDuel()
		b.Content.Units[actorID].MaxHP = 100000
		b.Values.Units[actorID].HP = hp
		b.Content.Units[actorID].Mech.Attack = 5250 // 4200 + 25%
		return resolveDuel(t, b)
	}

	assert.Equal(t, scaled(25000).main, at(25000, true).main, "HP at 25% holds")
	assert.Equal(t, at(25001, false).main, at(25001, true).main, "HP one above 25% does not")
}

// "When HP is 50% or below, increase own DEF by 10%" on the target: the
// main strike meets the scaled defense of a target at half HP.
func TestALowHPDefenseLineScalesTheDefenseOfTheStrikeTaken(t *testing.T) {
	line := lines.MechDefensePercentAtHPRateAtMost{Threshold: 50, Percent: 10}
	lined := scenarioDuel()
	lined.Content.Units[targetID].MaxHP = 100000
	lined.Values.Units[targetID].HP = 50000
	lined.Values.Units[targetID].SetAbilities([]ability.Line{line}, nil)
	stated := scenarioDuel()
	stated.Content.Units[targetID].MaxHP = 100000
	stated.Values.Units[targetID].HP = 50000
	stated.Content.Units[targetID].Mech.Defense = 4290 // 3900 + 10%

	assert.Equal(t, resolveDuel(t, stated).main, resolveDuel(t, lined).main)
}
