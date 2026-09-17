package board

import (
	"errors"
	"maps"
	"math/rand/v2"
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/system"
)

func (b *Board) Open(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, enemies []battle.Unit) error {
	return b.assemble(battle.BattleState{
		Units:        enemies,
		Phase:        battle.FactionAlly,
		Turn:         1,
		Bounds:       &bounds,
		Terrain:      terrain,
		TerrainCells: terrainCells,
	}, system.Fresh)
}

func (b *Board) Load(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, units []battle.Unit,
	phase battle.Faction, turn int) error {
	return b.assemble(battle.BattleState{
		Units:        units,
		Phase:        phase,
		Turn:         turn,
		Bounds:       &bounds,
		Terrain:      terrain,
		TerrainCells: terrainCells,
	}, system.Resumed)
}

func (b *Board) assemble(candidate battle.BattleState, origin system.Origin) error {
	content, values, err := system.Assemble(candidate, origin)
	if err != nil {
		return err
	}
	b.content, b.values = content, values
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
		Events:  events,
		Units:   b.affected(events),
		Outcome: system.Outcome(b.view()),
	}, nil
}

// The terminal values name every unit an effect landed on, in the order of
// the unit ids.
func (b *Board) affected(events []battle.Event) []battle.AffectedUnit {
	touched := map[int]bool{}
	for _, event := range events {
		for _, effect := range effectsOf(event) {
			touched[effect.UnitID] = true
		}
	}
	ids := slices.Sorted(maps.Keys(touched))
	out := make([]battle.AffectedUnit, 0, len(ids))
	for _, id := range ids {
		out = append(out, battle.AffectedUnit{UnitID: id, UnitValues: b.view().UnitValues(id)})
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
