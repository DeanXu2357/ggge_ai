package system

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

// A stage of two units with every maximum and count, and one map weapon on
// the enemy, before any value is set.
func stage() battle.BattleState {
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	unit := func(faction battle.Faction, x int) battle.Unit {
		return battle.Unit{Faction: faction, UnitValues: battle.UnitValues{Pos: battle.Cell{x, 0}},
			Mech: battle.Mech{HP: 100, EN: 50, MoveRange: 4}, Pilot: battle.Pilot{SP: 20},
			ChanceStepsMax: 1, SupportAttackChargesMax: 2, SupportDefendChargesMax: 3}
	}
	enemy := unit(battle.FactionEnemy, 3)
	enemy.Mech.MapWeapons = []battle.MapWeapon{{Name: "shells", AmmoMax: 4}}
	return battle.BattleState{Bounds: &bounds, Phase: battle.FactionAlly, Turn: 1,
		Units: []battle.Unit{unit(battle.FactionAlly, 0), enemy}}
}

// A battle in progress: the stage with the values of a moment.
func resumed() battle.BattleState {
	s := stage()
	for index := range s.Units {
		u := &s.Units[index]
		u.HP, u.EN, u.SP, u.MP, u.MoveRange = 60, 25, 10, 5, 3
		u.ChanceSteps, u.SupportAttackCharges, u.SupportDefendCharges = 1, 1, 2
		u.MapWeaponAmmo = make([]int, len(u.Mech.MapWeapons))
	}
	s.Units[1].MapWeaponAmmo[0] = 2
	s.Units[1].Debuffs = []battle.Debuff{{Kind: "armor", Magnitude: 0.1, AppliedPhase: 3}}
	s.Turn = 2
	return s
}

// A fresh battle sets every value of a unit to its default: the maxima, the
// counts, the ammunition of each map weapon, no debuff, not acted.
func TestAFreshBattleGivesEveryUnitItsDefaults(t *testing.T) {
	_, values, err := Assemble(stage(), Fresh)

	require.NoError(t, err)
	for id, unit := range values.Units {
		assert.Equal(t, []int{100, 50, 20, 0, 4}, []int{unit.HP, unit.EN, unit.SP, unit.MP, unit.MoveRange}, "unit %d fills its pools", id)
		assert.Equal(t, []int{1, 2, 3}, []int{unit.ChanceSteps, unit.SupportAttackCharges, unit.SupportDefendCharges}, "unit %d fills its counts", id)
		assert.False(t, unit.Acted)
		assert.Empty(t, unit.Debuffs)
	}
	assert.Equal(t, []int{}, values.Units[0].MapWeaponAmmo)
	assert.Equal(t, []int{4}, values.Units[1].MapWeaponAmmo)
}

// A fresh battle takes no value: a payload that states one is broken.
func TestAFreshBattleRefusesAStatedValue(t *testing.T) {
	for name, edit := range map[string]func(u *battle.Unit){
		"hp":                     func(u *battle.Unit) { u.HP = 1 },
		"en":                     func(u *battle.Unit) { u.EN = 1 },
		"sp":                     func(u *battle.Unit) { u.SP = 1 },
		"mp":                     func(u *battle.Unit) { u.MP = 1 },
		"move_range":             func(u *battle.Unit) { u.MoveRange = 1 },
		"acted":                  func(u *battle.Unit) { u.Acted = true },
		"chance_steps":           func(u *battle.Unit) { u.ChanceSteps = 1 },
		"support_attack_charges": func(u *battle.Unit) { u.SupportAttackCharges = 1 },
		"support_defend_charges": func(u *battle.Unit) { u.SupportDefendCharges = 1 },
		"map_weapon_ammo":        func(u *battle.Unit) { u.MapWeaponAmmo = []int{1} },
		"debuffs":                func(u *battle.Unit) { u.Debuffs = []battle.Debuff{{Kind: "armor"}} },
	} {
		t.Run(name, func(t *testing.T) {
			candidate := stage()
			edit(&candidate.Units[1])

			_, _, err := Assemble(candidate, Fresh)

			require.ErrorIs(t, err, battle.ErrOutsideContract)
			assert.Contains(t, err.Error(), "unit 1 states")
			assert.Contains(t, err.Error(), name)
		})
	}
}

// A resumed battle takes every value as given.
func TestAResumedBattleKeepsEveryValueAsGiven(t *testing.T) {
	_, values, err := Assemble(resumed(), Resumed)

	require.NoError(t, err)
	enemy := values.Units[1]
	assert.Equal(t, []int{60, 25, 10, 5, 3}, []int{enemy.HP, enemy.EN, enemy.SP, enemy.MP, enemy.MoveRange})
	assert.Equal(t, []int{1, 1, 2}, []int{enemy.ChanceSteps, enemy.SupportAttackCharges, enemy.SupportDefendCharges})
	assert.Equal(t, []int{2}, enemy.MapWeaponAmmo)
	assert.Len(t, enemy.Debuffs, 1)
}

// A resumed battle judges every value against its maximum.
func TestAResumedBattleRefusesAValueOutsideItsMaximum(t *testing.T) {
	for name, edit := range map[string]func(u *battle.Unit){
		"hp above the maximum":       func(u *battle.Unit) { u.HP = 101 },
		"hp below zero":              func(u *battle.Unit) { u.HP = -1 },
		"en above the maximum":       func(u *battle.Unit) { u.EN = 51 },
		"sp above the maximum":       func(u *battle.Unit) { u.SP = 21 },
		"mp above the maximum":       func(u *battle.Unit) { u.MP = 13 },
		"move range above the max":   func(u *battle.Unit) { u.MoveRange = 5 },
		"chance steps above the max": func(u *battle.Unit) { u.ChanceSteps = 2 },
		"support attack above max":   func(u *battle.Unit) { u.SupportAttackCharges = 3 },
		"support defend above max":   func(u *battle.Unit) { u.SupportDefendCharges = 4 },
		"ammunition above the max":   func(u *battle.Unit) { u.MapWeaponAmmo[0] = 5 },
		"an ammunition count short":  func(u *battle.Unit) { u.MapWeaponAmmo = []int{} },
		"a debuff from the future":   func(u *battle.Unit) { u.Debuffs[0].AppliedPhase = 99 },
	} {
		t.Run(name, func(t *testing.T) {
			candidate := resumed()
			edit(&candidate.Units[1])

			_, _, err := Assemble(candidate, Resumed)

			require.ErrorIs(t, err, battle.ErrOutsideContract)
			assert.Contains(t, err.Error(), "unit 1")
		})
	}
}

// A base of zero is a broken payload on both origins: the maximum is
// derived from it, and a maximum of zero is no pool.
func TestAssembleRefusesAUnitWhoseBaseIsZero(t *testing.T) {
	for name, tc := range map[string]struct {
		origin Origin
		edit   func(u *battle.Unit)
	}{
		"mech HP, fresh":    {Fresh, func(u *battle.Unit) { u.Mech.HP = 0 }},
		"mech EN, fresh":    {Fresh, func(u *battle.Unit) { u.Mech.EN = 0 }},
		"pilot SP, fresh":   {Fresh, func(u *battle.Unit) { u.Pilot.SP = 0 }},
		"mech HP, resumed":  {Resumed, func(u *battle.Unit) { u.Mech.HP = 0 }},
		"mech EN, resumed":  {Resumed, func(u *battle.Unit) { u.Mech.EN = 0 }},
		"pilot SP, resumed": {Resumed, func(u *battle.Unit) { u.Pilot.SP = 0 }},
	} {
		t.Run(name, func(t *testing.T) {
			candidate := stage()
			if tc.origin == Resumed {
				candidate = resumed()
			}
			tc.edit(&candidate.Units[1])

			_, _, err := Assemble(candidate, tc.origin)

			require.ErrorIs(t, err, battle.ErrOutsideContract)
			assert.Contains(t, err.Error(), "unit 1")
		})
	}
}

// Every refusal of the assembly is a payload outside the contract.
func TestAssembleRefusesAStateOutsideTheContractWithTheSentinel(t *testing.T) {
	for name, edit := range map[string]func(s *battle.BattleState){
		"no bounds":          func(s *battle.BattleState) { s.Bounds = nil },
		"backward bounds":    func(s *battle.BattleState) { s.Bounds = &battle.Bounds{{4, 4}, {0, 0}} },
		"an unknown phase":   func(s *battle.BattleState) { s.Phase = "pirate" },
		"an unknown faction": func(s *battle.BattleState) { s.Units[0].Faction = "pirate" },
		"a size below zero":  func(s *battle.BattleState) { s.Units[0].Size = battle.Cell{-1, 1} },
		"a unit outside":     func(s *battle.BattleState) { s.Units[0].Pos = battle.Cell{9, 9} },
		"a terrain cell outside": func(s *battle.BattleState) {
			s.TerrainCells = []battle.TerrainCell{{Cell: battle.Cell{9, 9}, Terrain: battle.TerrainGround}}
		},
	} {
		t.Run(name, func(t *testing.T) {
			candidate := stage()
			edit(&candidate)

			_, _, err := Assemble(candidate, Fresh)

			assert.True(t, errors.Is(err, battle.ErrOutsideContract), "error: %v", err)
		})
	}
}

func TestAssembleFillsWhatTheWireLeavesOut(t *testing.T) {
	content, _, err := Assemble(stage(), Fresh)

	require.NoError(t, err)
	assert.Equal(t, battle.TerrainSpace, content.Terrain, "an empty terrain becomes space")
	assert.Equal(t, battle.Cell{1, 1}, content.Units[0].Size, "a size of zero becomes one")
}

// Every maximum of the content is derived from the base data at assembly,
// on both origins; the payload states none.
func TestAssemblyDerivesTheMaximaFromTheBaseData(t *testing.T) {
	s := stage()
	s.Units[1].Mech.HP, s.Units[1].Mech.EN, s.Units[1].Pilot.SP, s.Units[1].Mech.MoveRange = 7000, 90, 30, 7

	for name, origin := range map[string]Origin{"fresh": Fresh, "resumed": Resumed} {
		t.Run(name, func(t *testing.T) {
			candidate := s
			if origin == Resumed {
				candidate = resumed()
				candidate.Units[1].Mech.HP, candidate.Units[1].Mech.EN = 7000, 90
				candidate.Units[1].Pilot.SP, candidate.Units[1].Mech.MoveRange = 30, 7
			}
			content, _, err := Assemble(candidate, origin)
			require.NoError(t, err)
			unit := content.Units[1]
			assert.Equal(t, []int{7000, 90, 30, 7, 0},
				[]int{unit.MaxHP, unit.ENMax, unit.SPMax, unit.MoveRange, unit.MPInitial})
		})
	}
}

// The reach of a unit reads the value of its move range and not the maximum.
func TestTheReachReadsTheMoveRangeValue(t *testing.T) {
	b := shootout()
	b.Content.Units[actorID].MoveRange = 2
	b.Values.Units[actorID].MoveRange = 0

	refused(t, b, battle.Action{ActorID: actorID, MoveTo: &battle.Cell{1, 0}}, battle.ErrIllegalMove)
}
