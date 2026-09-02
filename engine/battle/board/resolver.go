package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
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

func (b *Board) Act(action *battle.Decision, dice battle.Dice) (battle.ActResult, error) {
	engaged, trace, err := engagement.Commit(b.content, b.values, *action, dice)
	if err != nil {
		return battle.ActResult{}, err
	}
	rotated, rotations := turn.Advance(b.content, engaged)
	b.values = rotated
	var result battle.ActResult
	for _, strike := range trace {
		result.Strikes = append(result.Strikes, battle.StrikeEvent{
			Event: "strike", Strike: string(strike.Kind),
			ShooterID: strike.ShooterID, StruckID: strike.StruckID, WeaponID: strike.WeaponID,
			Landed: strike.Landed, Damage: strike.Damage, Killed: strike.Killed,
		})
	}
	for _, rotation := range rotations {
		result.Rotations = append(result.Rotations,
			battle.PhaseEvent{Event: "phase", Turn: rotation.Turn, Phase: rotation.Phase})
	}
	return result, nil
}
