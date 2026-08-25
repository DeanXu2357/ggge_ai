package battle

import (
	"errors"
	"reflect"
	"testing"
)

func coverIDs(options []SupportDefendOption) []string {
	out := make([]string, 0, len(options))
	for _, option := range options {
		out = append(out, option.Unit.ID)
	}
	return out
}

func stances(options []ReactionOption) []Stance {
	out := make([]Stance, 0, len(options))
	for _, option := range options {
		out = append(out, option.Stance)
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

func strike(cell Cell, weapon string) Decision {
	at := cell
	return Decision{UnitID: "e1", Kind: ActionAttack, MoveTo: &at, TargetID: "d1", Weapon: weapon}
}

func engagement(t *testing.T, state *Board, cell Cell, weapon string) Engagement {
	t.Helper()
	out, err := state.Reactions(strike(cell, weapon), "d1")
	if err != nil {
		t.Fatalf("reactions: %v", err)
	}
	return out
}

// The defender stands and takes the strike with 'none'. The shield is no
// answer of this command: it settles during the damage.
func TestTheReactionListHoldsTheStandAndNoShield(t *testing.T) {
	state := duel()

	out := engagement(t, state, Cell{1, 0}, "rifle")

	want := []Stance{StanceDodge, StanceDefend, StanceCounter, StanceNone}
	if !reflect.DeepEqual(stances(out.Reactions), want) {
		t.Fatalf("reactions: %v", stances(out.Reactions))
	}
}

func TestACounterWeaponNeedsTheReachTheEnergyAndThePermission(t *testing.T) {
	cases := map[string]func(weapon *Weapon){
		"a weapon that cannot counter": func(weapon *Weapon) { weapon.CanCounter = false },
		"a map weapon":                 func(weapon *Weapon) { weapon.MapWeapon = true },
		"a weapon it cannot pay for":   func(weapon *Weapon) { weapon.ENCost = 1000 },
		"a weapon out of its band":     func(weapon *Weapon) { weapon.Range = RadiusRange{Min: 3, Max: 4} },
	}

	for name, break_ := range cases {
		t.Run(name, func(t *testing.T) {
			state := duel()
			break_(&state.Unit("d1").Weapons[0])

			out := engagement(t, state, Cell{1, 0}, "rifle")

			want := []Stance{StanceDodge, StanceDefend, StanceNone}
			if !reflect.DeepEqual(stances(out.Reactions), want) {
				t.Fatalf("reactions: %v", stances(out.Reactions))
			}
		})
	}
}

// A stance carries no support unit: an interceptor changes no outcome of the
// stance, and it stands in its own list.
func TestTheTwoSidesCarryTheirOwnSupportUnits(t *testing.T) {
	state := duel()
	guard := unit("e2", FactionEnemy, Cell{2, 0})
	guard.MoveRange = 1
	guard.SupportDefendCharges = 1
	guard.SupportAttackCharges = 1
	guard.Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2})}
	state.Units = append(state.Units, guard)
	state.Unit("h1").SupportAttackCharges = 1
	state.Unit("h1").Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2})}

	out := engagement(t, state, Cell{1, 0}, "rifle")

	if len(out.Reactions) != 4 {
		t.Fatalf("the support units add no stance: %v", stances(out.Reactions))
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
	state.Unit("h1").MoveRange = 0
	state.Unit("h1").SupportAttackCharges = 1
	state.Unit("h1").Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2})}

	out := engagement(t, state, Cell{1, 0}, "rifle")

	if len(out.Defender.SupportDefenders) != 0 || len(out.Defender.SupportAttackers) != 0 {
		t.Fatalf("the support reach is the move range of the supporter: %+v", out.Defender)
	}
}

// Only an attack asks the defender anything, so the command refuses every
// other kind. A client that runs a map attack sends 'act' and no question.
func TestAnActionThatMakesNoStrikeIsAnError(t *testing.T) {
	state := duel()
	cell := Cell{4, 4}
	cases := map[string]Decision{
		"a map attack":             {UnitID: "e1", Kind: ActionMapAttack, Weapon: "rifle"},
		"a map attack out of band": {UnitID: "e1", Kind: ActionMapAttack, MoveTo: &cell, Weapon: "rifle"},
		"a standby":                {UnitID: "e1", Kind: ActionStandby},
		"a skill on the caster":    {UnitID: "e1", Kind: ActionSkillHeal},
	}

	for name, action := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := state.Reactions(action, "d1"); err == nil {
				t.Fatal("the action asks the defender nothing")
			}
		})
	}
}

func TestAReactionOfADestroyedUnitIsAnError(t *testing.T) {
	cases := map[string]string{"the defender": "d1", "the attacker": "e1"}

	for name, id := range cases {
		t.Run(name, func(t *testing.T) {
			state := duel()
			state.Unit(id).HP = 0

			_, err := state.Reactions(strike(Cell{1, 0}, "rifle"), "d1")

			if !errors.Is(err, ErrDestroyed) {
				t.Fatalf("error: %v", err)
			}
		})
	}
}

func TestTheStrikeComesFromTheCellOfTheAction(t *testing.T) {
	state := duel()

	near := engagement(t, state, Cell{1, 0}, "rifle")
	far := engagement(t, state, Cell{2, 0}, "rifle")

	if len(near.Reactions) != 4 || len(far.Reactions) != 3 {
		t.Fatalf("the counter of the defender reaches one cell: %v %v",
			stances(near.Reactions), stances(far.Reactions))
	}
}

func TestTheStrikeOfAnActionWithNoMoveComesFromTheCellOfToday(t *testing.T) {
	state := duel()

	out, err := state.Reactions(Decision{UnitID: "e1", Kind: ActionAttack, Weapon: "rifle"}, "d1")

	if err != nil {
		t.Fatalf("reactions: %v", err)
	}
	if len(out.Reactions) != 4 {
		t.Fatalf("unit 'e1' stands beside the defender: %v", stances(out.Reactions))
	}
}

func TestAReactionRequestOutsideTheBoardIsAnError(t *testing.T) {
	state := duel()
	cases := map[string]struct {
		defender, weapon string
		cell             Cell
	}{
		"an unknown defender":      {"ghost", "rifle", Cell{1, 0}},
		"an unknown weapon":        {"d1", "lance", Cell{1, 0}},
		"a weapon out of its band": {"d1", "rifle", Cell{3, 0}},
	}

	for name, one := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := state.Reactions(strike(one.cell, one.weapon), one.defender); err == nil {
				t.Fatal("the request stands outside the board")
			}
		})
	}
	if _, err := state.Reactions(strike(Cell{1, 0}, "rifle"), "d1"); err != nil {
		t.Fatalf("the request of the board: %v", err)
	}
	ghost := Decision{UnitID: "ghost", Kind: ActionAttack, Weapon: "rifle"}
	if _, err := state.Reactions(ghost, "d1"); !errors.Is(err, ErrNoUnit) {
		t.Fatalf("an unknown attacker: %v", err)
	}
}

func TestEachEntryCarriesTheForecastOfItsOwnStrike(t *testing.T) {
	attacker := fighter("e1", FactionEnemy, Cell{1, 0})
	attacker.Weapons = []Weapon{beam()}
	defender := fighter("d1", FactionAlly, Cell{0, 0})
	defender.Weapons = []Weapon{beam()}
	guard := fighter("h1", FactionAlly, Cell{0, 1})
	guard.MoveRange = 1
	guard.SupportDefendCharges = 1
	guard.SupportAttackCharges = 1
	guard.Weapons = []Weapon{beam()}
	state := board(defender, guard, attacker)

	out, err := state.Reactions(Decision{UnitID: "e1", Kind: ActionAttack,
		TargetID: "d1", Weapon: "beam rifle"}, "d1")
	if err != nil {
		t.Fatalf("reactions: %v", err)
	}

	byStance := map[Stance]ReactionOption{}
	for _, option := range out.Reactions {
		byStance[option.Stance] = option
	}
	dodge, defend, stand := byStance[StanceDodge], byStance[StanceDefend], byStance[StanceNone]
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
	counter := byStance[StanceCounter]
	if counter.Counter == nil || *counter.Counter.Damage <= 0 {
		t.Fatalf("a counter carries the forecast of its own strike: %+v", counter)
	}
	if *out.Defender.SupportDefenders[0].Incoming.Damage >= *stand.Incoming.Damage {
		t.Fatalf("an interceptor takes the strike in a defense state: %+v",
			out.Defender.SupportDefenders[0].Incoming)
	}
	if out.Defender.SupportDefenders[0].Incoming.HitRate != nil {
		t.Fatal("the hit roll of the strike stands beside the stance, not beside the interceptor")
	}
	if *out.Defender.SupportAttackers[0].Strike.Damage <= 0 ||
		out.Defender.SupportAttackers[0].Strike.Kill == nil {
		t.Fatalf("a support attacker carries the forecast of its own shot: %+v",
			out.Defender.SupportAttackers[0])
	}
}
