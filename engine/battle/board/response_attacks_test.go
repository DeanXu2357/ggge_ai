package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func coverIDs(options []supportDefendOption) []string {
	out := make([]string, 0, len(options))
	for _, option := range options {
		out = append(out, option.Unit.ID)
	}
	return out
}

func stances(options []responseAttackOption) []stance {
	out := make([]stance, 0, len(options))
	for _, option := range options {
		out = append(out, option.Stance)
	}
	return out
}

func duel() *Board {
	defender := unitAt("d1", factionAlly, cell{0, 0})
	defender.HasShield = true
	defender.Mech.Weapons = []weapon{rifle("saber", radiusRange{Min: 1, Max: 1})}
	helper := unitAt("h1", factionAlly, cell{0, 1})
	helper.Mech.MoveRange = 1
	helper.SupportDefendCharges = 1
	attacker := unitAt("e1", factionEnemy, cell{1, 0})
	attacker.Mech.Weapons = []weapon{rifle("rifle", radiusRange{Min: 1, Max: 2})}
	return board(defender, helper, attacker)
}

func strikeAction(cell cell, weapon string) decision {
	at := cell
	return decision{UnitID: "e1", Kind: actionAttack, MoveTo: &at, TargetID: "d1", Weapon: weapon}
}

func engagementOf(t *testing.T, state *Board, cell cell, weapon string) engagement {
	t.Helper()
	out, err := state.responseAttacks(strikeAction(cell, weapon), "d1")
	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}
	return out
}

// The defender stands and takes the strike with 'none'. The shield is no
// answer of this command: it settles during the damage.
func TestTheResponseAttackListHoldsTheStandAndNoShield(t *testing.T) {
	state := duel()

	out := engagementOf(t, state, cell{1, 0}, "rifle")

	want := []stance{stanceDodge, stanceDefend, stanceCounter, stanceNone}
	if !reflect.DeepEqual(stances(out.ResponseAttacks), want) {
		t.Fatalf("response attacks: %v", stances(out.ResponseAttacks))
	}
}

func TestACounterWeaponNeedsTheReachTheEnergyAndThePermission(t *testing.T) {
	cases := map[string]func(weapon *weapon){
		"a weapon that cannot counter": func(weapon *weapon) { weapon.CanCounter = false },
		"a map weapon":                 func(weapon *weapon) { weapon.MapWeapon = true },
		"a weapon it cannot pay for":   func(weapon *weapon) { weapon.ENCost = 1000 },
		"a weapon out of its band":     func(weapon *weapon) { weapon.Range = radiusRange{Min: 3, Max: 4} },
	}

	for name, break_ := range cases {
		t.Run(name, func(t *testing.T) {
			state := duel()
			break_(&state.unit("d1").Mech.Weapons[0])

			out := engagementOf(t, state, cell{1, 0}, "rifle")

			want := []stance{stanceDodge, stanceDefend, stanceNone}
			if !reflect.DeepEqual(stances(out.ResponseAttacks), want) {
				t.Fatalf("response attacks: %v", stances(out.ResponseAttacks))
			}
		})
	}
}

// A stance carries no support unit: a support defender changes no outcome of the
// stance, and it stands in its own list.
func TestTheTwoSidesCarryTheirOwnSupportUnits(t *testing.T) {
	state := duel()
	guard := unitAt("e2", factionEnemy, cell{2, 0})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	guard.SupportAttackCharges = 1
	guard.Mech.Weapons = []weapon{rifle("rifle", radiusRange{Min: 1, Max: 2})}
	state.units = append(state.units, guard)
	state.unit("h1").SupportAttackCharges = 1
	state.unit("h1").Mech.Weapons = []weapon{rifle("rifle", radiusRange{Min: 1, Max: 2})}

	out := engagementOf(t, state, cell{1, 0}, "rifle")

	if len(out.ResponseAttacks) != 4 {
		t.Fatalf("the support units add no stance: %v", stances(out.ResponseAttacks))
	}
	if !reflect.DeepEqual(coverIDs(out.Defender.SupportDefenders), []string{"h1"}) {
		t.Fatalf("the defender: %v", coverIDs(out.Defender.SupportDefenders))
	}
	if len(out.Defender.SupportAttackers) != 1 ||
		out.Defender.SupportAttackers[0].Unit.ID != "h1" {
		t.Fatalf("the defender joins with 'h1': %+v", out.Defender.SupportAttackers)
	}
	if !reflect.DeepEqual(coverIDs(out.Attacker.SupportDefenders), []string{"e2"}) {
		t.Fatalf("the attacker: %v", coverIDs(out.Attacker.SupportDefenders))
	}
	if len(out.Attacker.SupportAttackers) != 1 ||
		out.Attacker.SupportAttackers[0].Unit.ID != "e2" {
		t.Fatalf("the attacker joins with 'e2': %+v", out.Attacker.SupportAttackers)
	}
}

func TestASupporterOutOfItsMoveRangeJoinsNothing(t *testing.T) {
	state := duel()
	state.unit("h1").Mech.MoveRange = 0
	state.unit("h1").SupportAttackCharges = 1
	state.unit("h1").Mech.Weapons = []weapon{rifle("rifle", radiusRange{Min: 1, Max: 2})}

	out := engagementOf(t, state, cell{1, 0}, "rifle")

	if len(out.Defender.SupportDefenders) != 0 || len(out.Defender.SupportAttackers) != 0 {
		t.Fatalf("the support reach is the move range of the supporter: %+v", out.Defender)
	}
}

// Only an attack asks the defender anything, so the command refuses every
// other kind. A client that runs a map attack sends 'act' and no question.
func TestAnActionThatMakesNoStrikeIsAnError(t *testing.T) {
	state := duel()
	cell := cell{4, 4}
	cases := map[string]decision{
		"a map attack":             {UnitID: "e1", Kind: actionMapAttack, Weapon: "rifle"},
		"a map attack out of band": {UnitID: "e1", Kind: actionMapAttack, MoveTo: &cell, Weapon: "rifle"},
		"a standby":                {UnitID: "e1", Kind: actionStandby},
	}

	for name, action := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := state.responseAttacks(action, "d1"); err == nil {
				t.Fatal("the action asks the defender nothing")
			}
		})
	}
}

func TestAResponseAttackOfADestroyedUnitIsAnError(t *testing.T) {
	cases := map[string]string{"the defender": "d1", "the attacker": "e1"}

	for name, id := range cases {
		t.Run(name, func(t *testing.T) {
			state := duel()
			state.unit(id).HP = 0

			_, err := state.responseAttacks(strikeAction(cell{1, 0}, "rifle"), "d1")

			if !errors.Is(err, battle.ErrDestroyed) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}

func TestTheStrikeComesFromTheCellOfTheAction(t *testing.T) {
	state := duel()

	near := engagementOf(t, state, cell{1, 0}, "rifle")
	far := engagementOf(t, state, cell{2, 0}, "rifle")

	if len(near.ResponseAttacks) != 4 || len(far.ResponseAttacks) != 3 {
		t.Fatalf("the counter of the defender reaches one cell: %v %v",
			stances(near.ResponseAttacks), stances(far.ResponseAttacks))
	}
}

func TestTheStrikeOfAnActionWithNoMoveComesFromTheCellOfToday(t *testing.T) {
	state := duel()

	out, err := state.responseAttacks(decision{UnitID: "e1", Kind: actionAttack, Weapon: "rifle"}, "d1")

	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}
	if len(out.ResponseAttacks) != 4 {
		t.Fatalf("unit 'e1' stands beside the defender: %v", stances(out.ResponseAttacks))
	}
}

func TestAResponseAttackRequestOutsideTheBoardIsAnError(t *testing.T) {
	state := duel()
	cases := map[string]struct {
		defender, weapon string
		cell             cell
	}{
		"an unknown defender":      {"ghost", "rifle", cell{1, 0}},
		"an unknown weapon":        {"d1", "lance", cell{1, 0}},
		"a weapon out of its band": {"d1", "rifle", cell{3, 0}},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := state.responseAttacks(strikeAction(one.cell, one.weapon), one.defender); err == nil {
				t.Fatal("the request stands outside the board")
			}
		})
	}
	if _, err := state.responseAttacks(strikeAction(cell{1, 0}, "rifle"), "d1"); err != nil {
		t.Fatalf("the request of the board: %v", err)
	}
	ghost := decision{UnitID: "ghost", Kind: actionAttack, Weapon: "rifle"}
	if _, err := state.responseAttacks(ghost, "d1"); !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("an unknown attacker: %v", err)
	}
}

func TestEachEntryCarriesTheForecastOfItsOwnStrike(t *testing.T) {
	attacker := fighter("e1", factionEnemy, cell{1, 0})
	attacker.Mech.Weapons = []weapon{beam()}
	defender := fighter("d1", factionAlly, cell{0, 0})
	defender.Mech.Weapons = []weapon{beam()}
	guard := fighter("h1", factionAlly, cell{0, 1})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	guard.SupportAttackCharges = 1
	guard.Mech.Weapons = []weapon{beam()}
	state := board(defender, guard, attacker)

	out, err := state.responseAttacks(decision{UnitID: "e1", Kind: actionAttack,
		TargetID: "d1", Weapon: "beam rifle"}, "d1")
	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}

	byStance := map[stance]responseAttackOption{}
	for _, option := range out.ResponseAttacks {
		byStance[option.Stance] = option
	}
	dodge, defend, stand := byStance[stanceDodge], byStance[stanceDefend], byStance[stanceNone]
	if *dodge.Incoming.HitRate >= *stand.Incoming.HitRate {
		t.Fatalf("a dodge takes the hit rate down: %v against %v",
			*dodge.Incoming.HitRate, *stand.Incoming.HitRate)
	}
	if *defend.Incoming.Damage >= *stand.Incoming.Damage {
		t.Fatalf("a defense takes the damage down: %v against %v",
			*defend.Incoming.Damage, *stand.Incoming.Damage)
	}
	if *dodge.Incoming.Damage != *stand.Incoming.Damage {
		t.Fatal("a dodge that fails takes the whole damage")
	}
	counter := byStance[stanceCounter]
	if counter.Counter == nil || *counter.Counter.Damage <= 0 {
		t.Fatalf("a counter carries the forecast of its own strike: %+v", counter)
	}
	if *out.Defender.SupportDefenders[0].Incoming.Damage >= *stand.Incoming.Damage {
		t.Fatalf("a support defender takes the strike in a defense state: %+v",
			out.Defender.SupportDefenders[0].Incoming)
	}
	if out.Defender.SupportDefenders[0].Incoming.HitRate != nil {
		t.Fatal("the hit roll of the strike stands beside the stance, not beside the support defender")
	}
	if *out.Defender.SupportAttackers[0].Strike.Damage <= 0 ||
		out.Defender.SupportAttackers[0].Strike.Kill == nil {
		t.Fatalf("a support attacker carries the forecast of its own shot: %+v",
			out.Defender.SupportAttackers[0])
	}
}
