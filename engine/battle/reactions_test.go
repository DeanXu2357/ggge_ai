package battle

import (
	"errors"
	"reflect"
	"testing"
)

func stances(reactions []Reaction) []Stance {
	out := make([]Stance, 0, len(reactions))
	for _, reaction := range reactions {
		out = append(out, reaction.Stance)
	}
	return out
}

func duel() *Board {
	defender := unit("d1", FactionAlly, Cell{0, 0})
	defender.HasShield = true
	defender.Weapons = []Weapon{rifle("saber", RadiusRange{Min: 1, Max: 1})}
	helper := unit("h1", FactionAlly, Cell{0, 1})
	helper.MoveRange = 1
	helper.SupportDefendCharges = 1
	attacker := unit("e1", FactionEnemy, Cell{1, 0})
	attacker.Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2})}
	return board(defender, helper, attacker)
}

func reactions(t *testing.T, state *Board, cell Cell, weapon string) []Reaction {
	t.Helper()
	out, err := state.Reactions("d1", "e1", cell, weapon)
	if err != nil {
		t.Fatalf("reactions: %v", err)
	}
	return out
}

func TestTheReactionListHoldsNoDeclineOption(t *testing.T) {
	state := duel()
	state.Unit("h1").SupportDefendCharges = 0

	out := reactions(t, state, Cell{1, 0}, "rifle")

	want := []Stance{StanceDodge, StanceDefend, StanceShield, StanceCounter}
	if !reflect.DeepEqual(stances(out), want) {
		t.Fatalf("stances: %v", stances(out))
	}
	if out[3].Weapon != "saber" || !out[3].SupportAttack {
		t.Fatalf("counter: %+v", out[3])
	}
}

func TestADefenderWithNoShieldAndNoCounterKeepsDodgeAndDefend(t *testing.T) {
	state := duel()
	state.Unit("h1").SupportDefendCharges = 0
	state.Unit("d1").HasShield = false
	state.Unit("d1").Weapons[0].Range = RadiusRange{Min: 3, Max: 3}

	out := reactions(t, state, Cell{1, 0}, "rifle")

	if !reflect.DeepEqual(stances(out), []Stance{StanceDodge, StanceDefend}) {
		t.Fatalf("stances: %v", stances(out))
	}
}

func TestACounterWeaponNeedsTheReachTheEnergyAndThePermission(t *testing.T) {
	state := duel()
	state.Unit("h1").SupportDefendCharges = 0
	costly := rifle("costly", RadiusRange{Min: 1, Max: 1})
	costly.ENCost = 20
	passive := rifle("net", RadiusRange{Min: 1, Max: 1})
	passive.CanCounter = false
	shells := rifle("shells", RadiusRange{Min: 1, Max: 1})
	shells.MapWeapon = true
	state.Unit("d1").Weapons = []Weapon{costly, passive, shells,
		rifle("saber", RadiusRange{Min: 1, Max: 1})}
	state.Unit("d1").EN = 19

	out := reactions(t, state, Cell{1, 0}, "rifle")

	if len(out) != 4 || out[3].Weapon != "saber" {
		t.Fatalf("reactions: %+v", out)
	}
}

func TestSupportDefensePairsWithDodgeAndCounterAlone(t *testing.T) {
	out := reactions(t, duel(), Cell{1, 0}, "rifle")

	want := []Stance{
		StanceDodge, StanceDefend, StanceShield, StanceCounter,
		StanceDodge, StanceCounter,
	}
	if !reflect.DeepEqual(stances(out), want) {
		t.Fatalf("stances: %v", stances(out))
	}
	for _, reaction := range out {
		if reaction.SupportDefend &&
			(reaction.Stance == StanceDefend || reaction.Stance == StanceShield) {
			t.Fatalf("a defender that blocks the strike leaves the interceptor nothing: %+v",
				reaction)
		}
	}
}

func TestASupportAttackerAddsAVariantOfEveryOption(t *testing.T) {
	state := duel()
	state.Unit("h1").SupportAttackCharges = 1
	state.Unit("h1").Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2})}

	out := reactions(t, state, Cell{1, 0}, "rifle")

	if len(out) != 12 {
		t.Fatalf("reactions: %d", len(out))
	}
	for index, reaction := range out[:6] {
		if !reaction.SupportAttack || out[index+6].SupportAttack {
			t.Fatalf("the support attack is the default: %+v", out)
		}
	}
}

func TestASupporterOutOfItsMoveRangeJoinsNothing(t *testing.T) {
	state := duel()
	state.Unit("h1").MoveRange = 0
	state.Unit("h1").SupportAttackCharges = 1
	state.Unit("h1").Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2})}

	out := reactions(t, state, Cell{1, 0}, "rifle")

	if len(out) != 4 {
		t.Fatalf("reactions: %+v", out)
	}
}

func TestAMapWeaponPermitsNoReaction(t *testing.T) {
	state := duel()
	state.Unit("e1").Weapons[0].MapWeapon = true

	out := reactions(t, state, Cell{1, 0}, "rifle")

	if out == nil || len(out) != 0 {
		t.Fatalf("reactions: %v", out)
	}
}

func TestAMapWeaponOutOfItsBandPermitsNoReactionAndIsNoError(t *testing.T) {
	state := duel()
	state.Unit("e1").Weapons[0].MapWeapon = true

	out := reactions(t, state, Cell{4, 4}, "rifle")

	if out == nil || len(out) != 0 {
		t.Fatalf("the blast reaches a unit outside the band of the weapon: %v", out)
	}
}

func TestAReactionOfADestroyedUnitIsAnError(t *testing.T) {
	cases := map[string]string{"the defender": "d1", "the attacker": "e1"}

	for name, id := range cases {
		t.Run(name, func(t *testing.T) {
			state := duel()
			state.Unit(id).HP = 0

			_, err := state.Reactions("d1", "e1", Cell{1, 0}, "rifle")

			if !errors.Is(err, ErrDestroyed) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}

func TestTheStrikeComesFromTheCellOfTheRequest(t *testing.T) {
	state := duel()
	state.Unit("h1").SupportDefendCharges = 0

	near := reactions(t, state, Cell{1, 0}, "rifle")
	far := reactions(t, state, Cell{2, 0}, "rifle")

	if len(near) != 4 || len(far) != 3 {
		t.Fatalf("the counter of the defender reaches one cell: %v %v",
			stances(near), stances(far))
	}
}

func TestAReactionRequestOutsideTheBoardIsAnError(t *testing.T) {
	state := duel()
	cases := map[string]struct {
		defender, attacker, weapon string
		cell                       Cell
	}{
		"an unknown defender":      {"ghost", "e1", "rifle", Cell{1, 0}},
		"an unknown attacker":      {"d1", "ghost", "rifle", Cell{1, 0}},
		"an unknown weapon":        {"d1", "e1", "lance", Cell{1, 0}},
		"a weapon out of its band": {"d1", "e1", "rifle", Cell{3, 0}},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := state.Reactions(one.defender, one.attacker, one.cell, one.weapon); err == nil {
				t.Fatal("the request stands outside the board")
			}
		})
	}
}
