package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
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
			return fmt.Errorf("the unit %q stands outside the board", unit.ID)
		}
	}
	for _, entry := range candidate.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return fmt.Errorf("the terrain cell %v stands outside the board", entry.Cell)
		}
	}
	b.state = candidate.Clone()
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
	seen := make(map[string]bool, len(state.Units))
	for index := range state.Units {
		unit := &state.Units[index]
		if !knownFactions[unit.Faction] {
			return fmt.Errorf("unit %q carries the faction %q, which is not in the contract",
				unit.ID, unit.Faction)
		}
		if seen[unit.ID] {
			return fmt.Errorf("the board holds two units with the id %q", unit.ID)
		}
		seen[unit.ID] = true
		for axis := range unit.Size {
			if unit.Size[axis] < 0 {
				return fmt.Errorf("unit %q carries the size %v", unit.ID, unit.Size)
			}
		}
		unit.Size = unit.Footprint().Size
	}
	if state.Terrain == "" {
		state.Terrain = battle.TerrainSpace
	}
	return nil
}

type resolution struct {
	Trace     engagement.Trace
	Rotations []turn.Rotation
}

func (b *Board) Act(action *battle.Decision, dice battle.Dice) ([]any, error) {
	decision, err := decodeDecision(action)
	if err != nil {
		return nil, err
	}
	resolution, err := b.act(decision, dice)
	if err != nil {
		return nil, err
	}
	return encodeResolution(resolution), nil
}

func (b *Board) act(decision engagement.Decision, dice battle.Dice) (resolution, error) {
	plan, err := engagement.Prepare(&b.state, decision)
	if err != nil {
		return resolution{}, err
	}
	if !dice.Covers(plan.Draws()) {
		return resolution{}, fmt.Errorf(
			"%w: the 'outcomes' list holds fewer labels than the %d draws the action can make",
			battle.ErrOutsideContract, plan.Draws())
	}
	trace := engagement.Commit(&b.state, plan, dice)
	return resolution{Trace: trace, Rotations: turn.Advance(&b.state)}, nil
}

func encodeResolution(resolution resolution) []any {
	out := make([]any, 0, len(resolution.Trace)+len(resolution.Rotations))
	for _, strike := range resolution.Trace {
		out = append(out, battle.StrikeEvent{
			Event: "strike", Strike: string(strike.Kind),
			ShooterID: strike.ShooterID, StruckID: strike.StruckID, Weapon: strike.Weapon,
			Landed: strike.Landed, Damage: strike.Damage, Killed: strike.Killed,
		})
	}
	for _, rotation := range resolution.Rotations {
		out = append(out, battle.PhaseEvent{Event: "phase", Turn: rotation.Turn, Phase: rotation.Phase})
	}
	return out
}
