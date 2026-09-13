package system

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

type ledger struct {
	effects []battle.Effect
}

func (l *ledger) unit(id int) *battle.Effect {
	for index := range l.effects {
		if l.effects[index].UnitID == id {
			return &l.effects[index]
		}
	}
	l.effects = append(l.effects, battle.Effect{UnitID: id})
	return &l.effects[len(l.effects)-1]
}

func change[T any](field *T, to T) *battle.Change[T] {
	out := &battle.Change[T]{From: *field, To: to}
	*field = to
	return out
}

func changeDebuffs(field *[]battle.Debuff, to []battle.Debuff) *battle.Change[[]battle.Debuff] {
	out := &battle.Change[[]battle.Debuff]{From: slices.Clone(*field), To: slices.Clone(to)}
	*field = to
	return out
}
