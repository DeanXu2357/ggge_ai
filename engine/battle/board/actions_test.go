package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func rifle(name string, band def.RadiusRange) def.Weapon {
	return def.Weapon{Name: name, Range: band, UsableAfterMove: true}
}

func actionsOf(t *testing.T, b *Board, id string) protocol.ActionsResponse {
	t.Helper()
	out, err := b.Actions(id)
	if err != nil {
		t.Fatalf("actions: %v", err)
	}
	return out
}

func TestTheActionsCarryTheCellsTheUnitReaches(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("e1", state.FactionEnemy, state.Cell{1, 0}))
	b.state.Units[0].Mech.MoveRange = 1

	out := actionsOf(t, b, "a1")

	want := []protocol.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(out.MoveCells, want) {
		t.Fatalf("the foe blocks the cell (1,0): %v", out.MoveCells)
	}
	if out.Unit.UnitID != "a1" {
		t.Fatalf("unit: %v", out.Unit)
	}
}

// The command reads no resource and no band: a weapon with no energy left, a
// weapon that reaches nothing and a skill with no room all stay in the answer.
func TestTheActionsJudgeNoResourceAndNoBand(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("e1", state.FactionEnemy, state.Cell{4, 4}))
	costly := rifle("costly", def.RadiusRange{Min: 1, Max: 1})
	costly.ENCost = 20
	b.state.Units[0].EN = 0
	b.state.Units[0].Mech.Weapons = []def.Weapon{costly}
	b.state.Units[0].MaxHP = b.state.Units[0].HP
	b.state.Units[0].Skills = []state.Skill{{Kind: "skill_heal", Uses: 1}}

	out := actionsOf(t, b, "a1")

	if len(out.Weapons) != 1 || len(out.Skills) != 1 {
		t.Fatalf("the answer holds the whole panel: %+v", out)
	}
}

func TestAUnitThatActedKeepsItsActions(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{0, 0}))
	b.state.Units[0].Acted = true
	b.state.Units[0].Mech.MoveRange = 1

	out := actionsOf(t, b, "a1")

	if !out.Unit.Acted || len(out.MoveCells) == 0 {
		t.Fatalf("an acted unit answers with its cells and its state: %+v", out)
	}
}

func TestTheActionsOfAUnitThatCannotAnswerAreAnError(t *testing.T) {
	b := board(unitAt("a1", state.FactionAlly, state.Cell{0, 0}),
		unitAt("e1", state.FactionEnemy, state.Cell{2, 0}))
	dead := unitAt("a2", state.FactionAlly, state.Cell{0, 1})
	dead.HP = 0
	b.state.Units = append(b.state.Units, dead)
	cases := map[string]struct {
		unitID string
		want   error
	}{
		"an unknown unit":      {"ghost", battle.ErrNoUnit},
		"a destroyed unit":     {"a2", battle.ErrDestroyed},
		"a unit off the phase": {"e1", battle.ErrOffPhase},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := b.Actions(one.unitID)

			if !errors.Is(err, one.want) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}
