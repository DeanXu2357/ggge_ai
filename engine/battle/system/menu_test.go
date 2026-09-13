package system

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// The duel board stands the defender first, its helper second and the attacker
// third, so those three positions are the three ids.
const (
	duelDefenderID = 0
	duelHelperID   = 1
	duelAttackerID = 2
	duelGuardID    = 3
)

func coverIDs(options []SupportDefendOption) []int {
	out := make([]int, 0, len(options))
	for _, option := range options {
		out = append(out, option.UnitID)
	}
	return out
}

func stances(options []ResponseAttackOption) []battle.Stance {
	out := make([]battle.Stance, 0, len(options))
	for _, option := range options {
		out = append(out, option.Stance)
	}
	return out
}

func duelUnits() []battle.Unit {
	defender := unitAt(battle.FactionAlly, battle.Cell{0, 0})
	defender.HasShield = true
	defender.Mech.Weapons = []battle.Weapon{rifle("saber", 1, 1)}
	helper := unitAt(battle.FactionAlly, battle.Cell{0, 1})
	helper.Mech.MoveRange = 1
	helper.SupportDefendCharges = 1
	attacker := unitAt(battle.FactionEnemy, battle.Cell{1, 0})
	attacker.Mech.MoveRange = 2
	attacker.Mech.Weapons = []battle.Weapon{rifle("rifle", 1, 2)}
	return []battle.Unit{defender, helper, attacker}
}

func duelBoard(units ...battle.Unit) state.Battle {
	content, values := pair(units...)
	values.Phase = battle.FactionEnemy
	return state.Battle{Content: &content, Values: &values}
}

func duel() state.Battle {
	return duelBoard(duelUnits()...)
}

func strikeAction(cell battle.Cell, weaponID int) battle.Decision {
	at := cell
	return battle.Decision{UnitID: duelAttackerID, Kind: battle.ActionAttack, MoveTo: &at,
		TargetID: idOf(duelDefenderID), WeaponID: idOf(weaponID)}
}

func engagementOf(t *testing.T, b state.Battle, cell battle.Cell, weaponID int) Options {
	t.Helper()
	out, err := Menu(b, strikeAction(cell, weaponID), duelDefenderID)
	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}
	return out
}

// The defender stands and takes the strike with 'none'. The shield is no
// answer of this command: it settles during the damage.
func TestTheResponseAttackListHoldsTheStandAndNoShield(t *testing.T) {
	b := duel()

	out := engagementOf(t, b, battle.Cell{1, 0}, 0)

	want := []battle.Stance{battle.StanceDodge, battle.StanceDefend, battle.StanceCounter, battle.StanceNone}
	if !reflect.DeepEqual(stances(out.ResponseAttacks), want) {
		t.Fatalf("response attacks: %v", stances(out.ResponseAttacks))
	}
}

func TestACounterWeaponNeedsTheReachAndTheEnergy(t *testing.T) {
	cases := map[string]func(weapon *def.Weapon){
		"a weapon it cannot pay for": func(weapon *def.Weapon) { weapon.ENCost = 1000 },
		"a weapon out of its band": func(weapon *def.Weapon) {
			weapon.RangeMin, weapon.RangeMax = 3, 4
		},
	}

	for name, break_ := range cases {
		t.Run(name, func(t *testing.T) {
			b := duel()
			break_(&b.Content.Units[duelDefenderID].Mech.Weapons[0])

			out := engagementOf(t, b, battle.Cell{1, 0}, 0)

			want := []battle.Stance{battle.StanceDodge, battle.StanceDefend, battle.StanceNone}
			if !reflect.DeepEqual(stances(out.ResponseAttacks), want) {
				t.Fatalf("response attacks: %v", stances(out.ResponseAttacks))
			}
		})
	}
}

// The menu runs the plan of 'act', so an action that 'act' refuses carries no
// menu, with the same error.
func TestTheMenuRefusesWhatTheActionRefuses(t *testing.T) {
	b := duel()
	b.Content.Units[duelAttackerID].Mech.Weapons[0].ENCost = 1000
	decision := strikeAction(battle.Cell{1, 0}, 0)

	_, planned := prepare(b, decision)
	_, offered := Menu(b, decision, duelDefenderID)

	if planned == nil || offered == nil || offered.Error() != planned.Error() {
		t.Fatalf("the menu answers %v, and the action answers %v", offered, planned)
	}
	if !errors.Is(offered, battle.ErrIllegalAction) {
		t.Fatalf("error: %v", offered)
	}
}

// A stance carries no support unit: a support defender changes no outcome of the
// stance, and it stands in its own list.
func TestTheTwoSidesCarryTheirOwnSupportUnits(t *testing.T) {
	units := duelUnits()
	units[duelHelperID].SupportAttackCharges = 1
	units[duelHelperID].Mech.Weapons = []battle.Weapon{rifle("rifle", 1, 2)}
	guard := unitAt(battle.FactionEnemy, battle.Cell{2, 0})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	guard.SupportAttackCharges = 1
	guard.Mech.Weapons = []battle.Weapon{rifle("rifle", 1, 2)}
	b := duelBoard(append(units, guard)...)

	out := engagementOf(t, b, battle.Cell{1, 0}, 0)

	if len(out.ResponseAttacks) != 4 {
		t.Fatalf("the support units add no stance: %v", stances(out.ResponseAttacks))
	}
	if !reflect.DeepEqual(coverIDs(out.Defender.SupportDefenders), []int{duelHelperID}) {
		t.Fatalf("the defender: %v", coverIDs(out.Defender.SupportDefenders))
	}
	if len(out.Defender.SupportAttackers) != 1 ||
		out.Defender.SupportAttackers[0].UnitID != duelHelperID {
		t.Fatalf("the defender joins with its helper: %+v", out.Defender.SupportAttackers)
	}
	if !reflect.DeepEqual(coverIDs(out.Attacker.SupportDefenders), []int{duelGuardID}) {
		t.Fatalf("the attacker: %v", coverIDs(out.Attacker.SupportDefenders))
	}
	if len(out.Attacker.SupportAttackers) != 1 ||
		out.Attacker.SupportAttackers[0].UnitID != duelGuardID {
		t.Fatalf("the attacker joins with its guard: %+v", out.Attacker.SupportAttackers)
	}
}

func TestASupporterOutOfItsMoveRangeJoinsNothing(t *testing.T) {
	units := duelUnits()
	units[duelHelperID].Mech.MoveRange = 0
	units[duelHelperID].SupportAttackCharges = 1
	units[duelHelperID].Mech.Weapons = []battle.Weapon{rifle("rifle", 1, 2)}
	b := duelBoard(units...)

	out := engagementOf(t, b, battle.Cell{1, 0}, 0)

	if len(out.Defender.SupportDefenders) != 0 || len(out.Defender.SupportAttackers) != 0 {
		t.Fatalf("the support reach is the move range of the supporter: %+v", out.Defender)
	}
}

// Only an attack asks the defender anything, so the command refuses every
// other kind. A client that runs a map attack sends 'act' and no question.
func TestAnActionThatMakesNoStrikeIsAnError(t *testing.T) {
	b := duel()
	cell := battle.Cell{4, 4}
	cases := map[string]battle.Decision{
		"a map attack":             {UnitID: duelAttackerID, Kind: battle.ActionMapAttack},
		"a map attack out of band": {UnitID: duelAttackerID, Kind: battle.ActionMapAttack, MoveTo: &cell},
		"a standby":                {UnitID: duelAttackerID, Kind: battle.ActionStandby},
	}

	for name, decision := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := Menu(b, decision, duelDefenderID); err == nil {
				t.Fatal("the action asks the defender nothing")
			}
		})
	}
}

func TestAResponseAttackOfADestroyedUnitIsAnError(t *testing.T) {
	cases := []struct {
		name   string
		unitID int
	}{{"the defender", duelDefenderID}, {"the attacker", duelAttackerID}}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			b := duelBoard(append(duelUnits(), unitAt(battle.FactionEnemy, battle.Cell{4, 4}))...)
			b.Values.Units[one.unitID].HP = 0

			_, err := Menu(b, strikeAction(battle.Cell{1, 0}, 0), duelDefenderID)

			if !errors.Is(err, battle.ErrDestroyed) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}

func TestTheStrikeComesFromTheCellOfTheAction(t *testing.T) {
	b := duel()

	near := engagementOf(t, b, battle.Cell{1, 0}, 0)
	far := engagementOf(t, b, battle.Cell{2, 0}, 0)

	if len(near.ResponseAttacks) != 4 || len(far.ResponseAttacks) != 3 {
		t.Fatalf("the counter of the defender reaches one cell: %v %v",
			stances(near.ResponseAttacks), stances(far.ResponseAttacks))
	}
}

func TestTheStrikeOfAnActionWithNoMoveComesFromTheCellOfToday(t *testing.T) {
	b := duel()

	out, err := Menu(b, battle.Decision{UnitID: duelAttackerID,
		Kind: battle.ActionAttack, TargetID: idOf(duelDefenderID), WeaponID: idOf(0)},
		duelDefenderID)

	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}
	if len(out.ResponseAttacks) != 4 {
		t.Fatalf("the attacker stands beside the defender: %v", stances(out.ResponseAttacks))
	}
}

func TestAResponseAttackRequestOutsideTheBoardIsAnError(t *testing.T) {
	b := duel()
	cases := map[string]struct {
		defenderID, weaponID int
		cell                 battle.Cell
	}{
		"an unknown defender":      {9, 0, battle.Cell{1, 0}},
		"an unknown weapon":        {duelDefenderID, 9, battle.Cell{1, 0}},
		"a weapon out of its band": {duelDefenderID, 0, battle.Cell{3, 0}},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := Menu(b, strikeAction(one.cell, one.weaponID),
				one.defenderID); err == nil {
				t.Fatal("the request stands outside the board")
			}
		})
	}
	if _, err := Menu(b, strikeAction(battle.Cell{1, 0}, 0),
		duelDefenderID); err != nil {
		t.Fatalf("the request of the board: %v", err)
	}
	ghost := battle.Decision{UnitID: 9, Kind: battle.ActionAttack, WeaponID: idOf(0)}
	if _, err := Menu(b, ghost, duelDefenderID); !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("an unknown attacker: %v", err)
	}
}

func TestEachEntryCarriesTheForecastOfItsOwnStrike(t *testing.T) {
	defender := fighter(battle.FactionAlly, battle.Cell{0, 0})
	defender.Mech.Weapons = []battle.Weapon{beam()}
	guard := fighter(battle.FactionAlly, battle.Cell{0, 1})
	guard.Mech.MoveRange = 1
	guard.SupportDefendCharges = 1
	guard.SupportAttackCharges = 1
	guard.Mech.Weapons = []battle.Weapon{beam()}
	attacker := fighter(battle.FactionEnemy, battle.Cell{1, 0})
	attacker.Mech.Weapons = []battle.Weapon{beam()}
	b := duelBoard(defender, guard, attacker)

	out, err := Menu(b, battle.Decision{UnitID: duelAttackerID,
		Kind: battle.ActionAttack, TargetID: idOf(duelDefenderID), WeaponID: idOf(0)},
		duelDefenderID)
	if err != nil {
		t.Fatalf("response attacks: %v", err)
	}

	byStance := map[battle.Stance]ResponseAttackOption{}
	for _, option := range out.ResponseAttacks {
		byStance[option.Stance] = option
	}
	dodge, defend, stand := byStance[battle.StanceDodge], byStance[battle.StanceDefend], byStance[battle.StanceNone]
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
	counter := byStance[battle.StanceCounter]
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
