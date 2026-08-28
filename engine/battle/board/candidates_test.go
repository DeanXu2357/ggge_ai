package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func rifle(name string, band RadiusRange) Weapon {
	return Weapon{Name: name, Range: band, CanCounter: true, UsableAfterMove: true}
}

func capabilities(t *testing.T, state *Board, id string) Capabilities {
	t.Helper()
	out, err := state.capabilities(id)
	if err != nil {
		t.Fatalf("capabilities: %v", err)
	}
	return out
}

func TestTheCapabilitiesCarryTheCellsTheUnitReaches(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{1, 0}))
	state.units[0].Mech.MoveRange = 1

	out := capabilities(t, state, "a1")

	want := []Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(out.MoveCells, want) {
		t.Fatalf("the foe blocks the cell (1,0): %v", out.MoveCells)
	}
	if out.Unit.ID != "a1" {
		t.Fatalf("unit: %v", out.Unit)
	}
}

// The command reads no resource and no band: a weapon with no energy left, a
// weapon that reaches nothing and a skill with no room all stay in the answer.
func TestTheCapabilitiesJudgeNoResourceAndNoBand(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{4, 4}))
	costly := rifle("costly", RadiusRange{Min: 1, Max: 1})
	costly.ENCost = 20
	state.units[0].EN = 0
	state.units[0].Mech.Weapons = []Weapon{costly}
	state.units[0].MaxHP = state.units[0].HP
	state.units[0].Skills = []Skill{{Kind: "skill_heal", Uses: 1}}

	out := capabilities(t, state, "a1")

	if len(out.Unit.Mech.Weapons) != 1 || len(out.Unit.Skills) != 1 {
		t.Fatalf("the answer holds the whole panel: %+v", out.Unit)
	}
}

func TestAUnitThatActedKeepsItsCapabilities(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}))
	state.units[0].Acted = true
	state.units[0].Mech.MoveRange = 1

	out := capabilities(t, state, "a1")

	if !out.Unit.Acted || len(out.MoveCells) == 0 {
		t.Fatalf("an acted unit answers with its cells and its state: %+v", out)
	}
}

func TestTheCapabilitiesOfAUnitThatCannotAnswerAreAnError(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{2, 0}))
	dead := unit("a2", FactionAlly, Cell{0, 1})
	dead.HP = 0
	state.units = append(state.units, dead)
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
			_, err := state.capabilities(one.unitID)

			if !errors.Is(err, one.want) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}
