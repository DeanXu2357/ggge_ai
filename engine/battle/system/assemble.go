package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var knownFactions = map[battle.Faction]bool{
	battle.FactionAlly:       true,
	battle.FactionEnemy:      true,
	battle.FactionThirdParty: true,
}

func Assemble(candidate battle.BattleState) (state.Content, state.Values, error) {
	if err := validate(&candidate); err != nil {
		return state.Content{}, state.Values{}, err
	}
	content, values := state.FromContract(candidate)
	return content, values, nil
}

func validate(s *battle.BattleState) error {
	if s.Bounds == nil {
		return fmt.Errorf("the state carries no bounds")
	}
	bounds := *s.Bounds
	if bounds[1][0] < bounds[0][0] || bounds[1][1] < bounds[0][1] {
		return fmt.Errorf("the bounds %v run backward", bounds)
	}
	if !knownFactions[s.Phase] {
		return fmt.Errorf("the state carries the phase %q, which is not in the contract",
			s.Phase)
	}
	for index := range s.Units {
		if err := validateUnit(index, &s.Units[index], bounds); err != nil {
			return err
		}
	}
	for _, entry := range s.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return fmt.Errorf("the terrain cell %v stands outside the board", entry.Cell)
		}
	}
	if s.Terrain == "" {
		s.Terrain = battle.TerrainSpace
	}
	return nil
}

// SP is not judged: no rule of this version reads it, and every state of the
// repository carries zero.
func validateUnit(index int, u *battle.Unit, bounds battle.Bounds) error {
	if !knownFactions[u.Faction] {
		return fmt.Errorf("unit %d carries the faction %q, which is not in the contract",
			index, u.Faction)
	}
	if len(u.MapWeaponAmmo) != len(u.Mech.MapWeapons) {
		return fmt.Errorf("unit %d carries %d ammunition counts and %d map weapons",
			index, len(u.MapWeaponAmmo), len(u.Mech.MapWeapons))
	}
	for axis := range u.Size {
		if u.Size[axis] < 0 {
			return fmt.Errorf("unit %d carries the size %v", index, u.Size)
		}
	}
	u.Size = u.Footprint().Size
	if !u.Footprint().Within(bounds) {
		return fmt.Errorf("the unit %d stands outside the board", index)
	}
	if u.MaxHP <= 0 {
		return fmt.Errorf("unit %d carries the maximum HP %d", index, u.MaxHP)
	}
	if u.ENMax <= 0 {
		return fmt.Errorf("unit %d carries the maximum EN %d", index, u.ENMax)
	}
	return nil
}
