package state

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// A line with its own state: it counts the strikes its holder fired.
type countingLine struct{ fired int }

func (l *countingLine) Clone() ability.Line             { c := *l; return &c }
func (l *countingLine) OnAttack(*ability.AttackContext) { l.fired++ }

func TestACloneOfTheValuesOwnsItsLinesAndTheirChains(t *testing.T) {
	original := &countingLine{}
	values := Values{Units: []UnitValue{{}}}
	values.Units[0].SetAbilities([]ability.Line{original}, nil)

	cloned := values.Clone()
	cloned.Units[0].Hooks.Attack(&ability.AttackContext{})

	assert.Equal(t, 1, cloned.Units[0].MechAbilities[0].(*countingLine).fired, "the chain of the clone fires the line of the clone")
	assert.Equal(t, 0, original.fired, "the line of the original is untouched")
	assert.NotSame(t, original, cloned.Units[0].MechAbilities[0], "the clone holds a copy of the line")
}
