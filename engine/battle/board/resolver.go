package board

import (
	"errors"
	"fmt"
	"maps"
	"math/rand/v2"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/system"
)

func (b *Board) Load(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, units []battle.Unit,
	phase battle.Faction, turn int) error {
	candidate := battle.BattleState{
		Units:        units,
		Phase:        phase,
		Turn:         turn,
		Bounds:       &bounds,
		Terrain:      terrain,
		TerrainCells: terrainCells,
	}
	for index := range candidate.Units {
		assemble(&candidate.Units[index])
	}
	if err := validate(&candidate); err != nil {
		return err
	}
	for index := range candidate.Units {
		unit := &candidate.Units[index]
		if !unit.Footprint().Within(bounds) {
			return fmt.Errorf("the unit %d stands outside the board", index)
		}
	}
	for _, entry := range candidate.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return fmt.Errorf("the terrain cell %v stands outside the board", entry.Cell)
		}
	}
	b.content, b.values = state.FromContract(candidate)
	return nil
}

// A maximum that the payload leaves at zero comes from the pairing. An
// explicit value stands: an ability of the pilot or of the mech can lift the
// maximum above the base data (issue #77).
func assemble(unit *battle.Unit) {
	if unit.MaxHP == 0 {
		unit.MaxHP = unit.Mech.HP
	}
	if unit.ENMax == 0 {
		unit.ENMax = unit.Mech.EN
	}
	if unit.SPMax == 0 {
		unit.SPMax = unit.Pilot.SP
	}
}

var knownFactions = map[battle.Faction]bool{
	battle.FactionAlly:       true,
	battle.FactionEnemy:      true,
	battle.FactionThirdParty: true,
}

// Validate judges every fact of a state that the JSON decode cannot, and it
// fills the two values that the wire leaves out: a size of zero and an empty
// terrain.
func validate(state *battle.BattleState) error {
	if state.Bounds == nil {
		return fmt.Errorf("the state carries no bounds")
	}
	bounds := *state.Bounds
	if bounds[1][0] < bounds[0][0] || bounds[1][1] < bounds[0][1] {
		return fmt.Errorf("the bounds %v run backward", bounds)
	}
	if !knownFactions[state.Phase] {
		return fmt.Errorf("the state carries the phase %q, which is not in the contract",
			state.Phase)
	}
	for index := range state.Units {
		unit := &state.Units[index]
		if !knownFactions[unit.Faction] {
			return fmt.Errorf("unit %d carries the faction %q, which is not in the contract",
				index, unit.Faction)
		}
		if len(unit.MapWeaponAmmo) != len(unit.Mech.MapWeapons) {
			return fmt.Errorf("unit %d carries %d ammunition counts and %d map weapons",
				index, len(unit.MapWeaponAmmo), len(unit.Mech.MapWeapons))
		}
		for axis := range unit.Size {
			if unit.Size[axis] < 0 {
				return fmt.Errorf("unit %d carries the size %v", index, unit.Size)
			}
		}
		unit.Size = unit.Footprint().Size
	}
	if state.Terrain == "" {
		state.Terrain = battle.TerrainSpace
	}
	return nil
}

func (b *Board) Act(action *battle.Action) (battle.ActResult, error) {
	before, err := b.source.MarshalBinary()
	if err != nil {
		return battle.ActResult{}, err
	}
	engaged, events, err := system.Commit(b.view(), *action, rand.New(b.source))
	if err != nil {
		return battle.ActResult{}, errors.Join(err, b.source.UnmarshalBinary(before))
	}
	b.values = engaged
	return battle.ActResult{
		Events: events,
		Units:  b.affected(events),
	}, nil
}

// The terminal values name every unit an effect landed on, in the order of
// the unit ids.
func (b *Board) affected(events []battle.Event) []battle.UnitValues {
	touched := map[int]bool{}
	for _, event := range events {
		for _, effect := range effectsOf(event) {
			touched[effect.UnitID] = true
		}
	}
	ids := slices.Sorted(maps.Keys(touched))
	out := make([]battle.UnitValues, 0, len(ids))
	for _, id := range ids {
		out = append(out, b.view().UnitValues(id))
	}
	return out
}

func effectsOf(event battle.Event) []battle.Effect {
	switch e := event.(type) {
	case battle.StrikeEvent:
		return e.Effects
	case battle.ActivationEndEvent:
		return e.Effects
	case battle.PhaseEvent:
		return e.Effects
	}
	return nil
}
