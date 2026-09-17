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

const zeonTagID = 1015

// duelExchange is the exchange of the duel on the board, for a forecast: the
// actor against the target, no draw.
func duelExchange(b state.Battle) *exchange {
	return &exchange{board: b, cast: cast{actorID: actorID, targetID: targetID}}
}

type exchangeDamage struct {
	main, counter int
}

// A scenario board: the actor at (0,0) and the target at (3,0), each with one
// beam of reach 3, and an HP that no strike of the pair reaches.
func scenarioDuel() state.Battle {
	beamRifle := battle.Weapon{Name: "beam rifle", Power: 1800, RangeMin: 1, RangeMax: 3,
		ENCost: 10, Accuracy: 5, UsableAfterMove: true}
	pilot := battle.Pilot{Ranged: 220, Melee: 220, Awaken: 220, Defense: 190, Reaction: 205}
	mech := battle.Mech{Attack: 4200, Defense: 3900, Mobility: 310, Weapons: []battle.Weapon{beamRifle}}
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	content, values := assembled(battle.BattleState{
		Bounds: &bounds, Phase: battle.FactionAlly, Turn: 1,
		Units: []battle.Unit{
			{Faction: battle.FactionAlly, Pos: battle.Cell{0, 0}, Size: battle.Cell{1, 1},
				HP: 99000, MaxHP: 99000, EN: 140, ENMax: 140, Pilot: pilot, Mech: mech},
			{Faction: battle.FactionEnemy, Pos: battle.Cell{3, 0}, Size: battle.Cell{1, 1},
				HP: 99000, MaxHP: 99000, EN: 140, ENMax: 140, Pilot: pilot, Mech: mech},
		},
	})
	return state.Battle{Content: &content, Values: &values}
}

// The actor fires at the target, the target counters, both strikes land.
func resolveDuel(t *testing.T, b state.Battle) exchangeDamage {
	t.Helper()
	_, events := accepted(t, b, battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: hit()},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0), Stated: hit()}})

	got := strikes(events)

	require.Len(t, got, 2)
	require.Equal(t, battle.SegmentMain, got[0].Segment)
	require.Equal(t, battle.SegmentCounter, got[1].Segment)
	require.Positive(t, got[0].Damage, "the main strike does damage")
	require.Positive(t, got[1].Damage, "the counter does damage")
	return exchangeDamage{main: got[0].Damage, counter: got[1].Damage}
}

// The "Advantage: Principality of Zeon" ability of the sample store: ATK and
// DEF +15% against enemies that carry the tag 1015.
func advantageAgainstZeon() []ability.Line {
	return []ability.Line{
		lines.MechAttackPercentAgainstTag{EnemyTag: zeonTagID, Percent: 15},
		lines.MechDefensePercentAgainstTag{EnemyTag: zeonTagID, Percent: 15},
	}
}

// The target holds the ability and the actor carries the tag. The main
// strike does the damage of a defender whose defense is already scaled, and
// the counter the damage of an attacker whose attack is already scaled.
func TestAdvantageScalesTheDefenseInTheMainStrikeAndTheAttackInTheCounter(t *testing.T) {
	plainBoard := scenarioDuel()
	plainBoard.Content.Units[actorID].Mech.Tags = []int{zeonTagID}
	plain := resolveDuel(t, plainBoard)

	hooked := scenarioDuel()
	hooked.Content.Units[actorID].Mech.Tags = []int{zeonTagID}
	hooked.Values.Units[targetID].SetAbilities(advantageAgainstZeon())
	withHooks := resolveDuel(t, hooked)

	stated := scenarioDuel()
	stated.Content.Units[actorID].Mech.Tags = []int{zeonTagID}
	stated.Content.Units[targetID].Mech.Attack = 4830  // 4200 + 15%
	stated.Content.Units[targetID].Mech.Defense = 4485 // 3900 + 15%
	withStats := resolveDuel(t, stated)

	assert.Equal(t, withStats, withHooks, "the hooks give the exchange of the stated stats")
	assert.Less(t, withHooks.main, plain.main, "the scaled defense lowers the main strike")
	assert.Greater(t, withHooks.counter, plain.counter, "the scaled attack raises the counter")
}

// The ability reads the tag of the enemy, not the tag of its own mech: a
// holder that carries the tag itself, against an enemy without it, meets no
// condition.
func TestAdvantageReadsTheTagOfTheEnemyAndNotItsOwn(t *testing.T) {
	plainBoard := scenarioDuel()
	plainBoard.Content.Units[targetID].Mech.Tags = []int{zeonTagID}
	plain := resolveDuel(t, plainBoard)

	hooked := scenarioDuel()
	hooked.Content.Units[targetID].Mech.Tags = []int{zeonTagID}
	hooked.Values.Units[targetID].SetAbilities(advantageAgainstZeon())

	assert.Equal(t, plain, resolveDuel(t, hooked), "an enemy without the tag meets no hook")
}
