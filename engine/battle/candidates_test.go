package battle

import (
	"reflect"
	"testing"
)

func rifle(name string, band RadiusRange) Weapon {
	return Weapon{Name: name, Range: band, CanCounter: true, UsableAfterMove: true}
}

func actions(t *testing.T, state *Board, id string) []Decision {
	t.Helper()
	out, err := state.Actions(id)
	if err != nil {
		t.Fatalf("actions: %v", err)
	}
	return out
}

func kinds(decisions []Decision) []ActionKind {
	out := make([]ActionKind, 0, len(decisions))
	for _, decision := range decisions {
		out = append(out, decision.Kind)
	}
	return out
}

func TestAnAttackNamesTheAnchorInTheBandNearestToTheUnit(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{4, 0}))
	state.Units[0].MoveRange = 4
	state.Units[0].Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 2, Max: 2})}

	out := actions(t, state, "a1")

	if out[0].Kind != ActionAttack {
		t.Fatalf("actions: %+v", kinds(out))
	}
	if out[0].TargetID != "e1" || out[0].Weapon != "rifle" {
		t.Fatalf("attack: %+v", out[0])
	}
	if out[0].MoveTo == nil || *out[0].MoveTo != (Cell{2, 0}) {
		t.Fatalf("the anchor (3,1) is also in the band and stands farther away: %+v", out[0].MoveTo)
	}
}

func TestAWeaponThatIsNotUsableAfterMoveFiresFromTheAnchorOfToday(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{4, 0}))
	state.Units[0].MoveRange = 4
	near := rifle("near", RadiusRange{Min: 2, Max: 2})
	near.UsableAfterMove = false
	far := rifle("far", RadiusRange{Min: 4, Max: 4})
	far.UsableAfterMove = false
	state.Units[0].Weapons = []Weapon{near, far}

	out := actions(t, state, "a1")

	if out[0].Kind != ActionAttack || out[0].Weapon != "far" {
		t.Fatalf("a weapon that fires before the move reaches no other anchor: %+v", out)
	}
	if out[0].MoveTo != nil {
		t.Fatalf("move: %+v", out[0].MoveTo)
	}
	if out[1].Kind == ActionAttack {
		t.Fatalf("the weapon 'near' reaches the band from no anchor of today: %+v", out[1])
	}
}

func TestAWeaponWithNoEnergyLeftNamesNoCandidate(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{1, 0}))
	costly := rifle("costly", RadiusRange{Min: 1, Max: 1})
	costly.ENCost = 20
	state.Units[0].Weapons = []Weapon{rifle("free", RadiusRange{Min: 1, Max: 1}), costly}
	state.Units[0].EN = 19

	out := actions(t, state, "a1")

	if len(out) != 2 || out[0].Weapon != "free" {
		t.Fatalf("actions: %+v", out)
	}
}

func TestAFootprintFiresAtTheDistanceBetweenTheFootprints(t *testing.T) {
	wide := unit("a1", FactionAlly, Cell{0, 0})
	wide.Footprint.Size = Size{2, 2}
	wide.Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 1})}
	state := board(wide, unit("e1", FactionEnemy, Cell{2, 0}))

	out := actions(t, state, "a1")

	if len(out) != 2 || out[0].Kind != ActionAttack {
		t.Fatalf("the anchors stand two cells apart, and the footprints touch: %+v", out)
	}
	if out[0].MoveTo != nil {
		t.Fatalf("move: %+v", out[0].MoveTo)
	}
}

func TestAMapAttackNamesTheAnchorOfTheTargetAndNoTarget(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{3, 0}))
	loaded := rifle("loaded", RadiusRange{Min: 1, Max: 4})
	loaded.MapWeapon = true
	empty := rifle("empty", RadiusRange{Min: 1, Max: 4})
	empty.MapWeapon = true
	state.Units[0].Weapons = []Weapon{loaded, empty}
	state.Units[0].Ammo = map[string]int{"loaded": 1, "empty": 0}

	out := actions(t, state, "a1")

	if len(out) != 2 || out[0].Kind != ActionMapAttack || out[0].Weapon != "loaded" {
		t.Fatalf("a map weapon with no ammunition names no candidate: %+v", out)
	}
	if out[0].TargetID != "" || out[0].Aim == nil || *out[0].Aim != (Cell{3, 0}) {
		t.Fatalf("map attack: %+v", out[0])
	}
}

func TestASkillIsNamedOnlyWhenItsEffectHasRoom(t *testing.T) {
	amount := 3000.0
	state := board(unit("a1", FactionAlly, Cell{0, 0}), unit("e1", FactionEnemy, Cell{4, 4}))
	state.Units[0].MaxHP = 100
	state.Units[0].EN = 10
	state.Units[0].ENMax = 40
	state.Units[0].Skills = []Skill{
		{Kind: ActionSkillHeal, Amount: &amount, Uses: 1},
		{Kind: ActionSkillRefill, Uses: 1},
		{Kind: ActionSkillRefill, Uses: 0},
	}

	out := actions(t, state, "a1")

	if !reflect.DeepEqual(kinds(out), []ActionKind{ActionSkillRefill, ActionStandby}) {
		t.Fatalf("a unit at full hit points needs no heal: %+v", kinds(out))
	}
	if out[0].Amount != nil {
		t.Fatalf("amount: %v", *out[0].Amount)
	}
}

func TestARepositionNamesTheAnchorNearTheTargetAndTheAnchorAwayFromIt(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{2, 2}), unit("e1", FactionEnemy, Cell{4, 2}))
	state.Units[0].MoveRange = 1

	out := actions(t, state, "a1")

	if !reflect.DeepEqual(kinds(out), []ActionKind{ActionReposition, ActionReposition, ActionStandby}) {
		t.Fatalf("actions: %+v", kinds(out))
	}
	if *out[0].MoveTo != (Cell{3, 2}) || *out[1].MoveTo != (Cell{1, 2}) {
		t.Fatalf("the picks are the near anchor and the far anchor: %+v %+v", out[0], out[1])
	}
}

func TestAUnitThatCannotMoveNamesNoReposition(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{2, 2}), unit("e1", FactionEnemy, Cell{4, 2}))

	out := actions(t, state, "a1")

	if !reflect.DeepEqual(kinds(out), []ActionKind{ActionStandby}) {
		t.Fatalf("actions: %+v", kinds(out))
	}
}

func TestTheActionsComeInOneOrderOnEveryCall(t *testing.T) {
	amount := 3000.0
	state := board(
		unit("a1", FactionAlly, Cell{0, 0}),
		unit("e1", FactionEnemy, Cell{1, 0}),
		unit("e2", FactionEnemy, Cell{0, 2}),
	)
	shells := rifle("shells", RadiusRange{Min: 1, Max: 4})
	shells.MapWeapon = true
	state.Units[0].MoveRange = 1
	state.Units[0].MaxHP = 200
	state.Units[0].Weapons = []Weapon{rifle("rifle", RadiusRange{Min: 1, Max: 2}), shells}
	state.Units[0].Ammo = map[string]int{"shells": 2}
	state.Units[0].Skills = []Skill{{Kind: ActionSkillHeal, Amount: &amount, Uses: 1}}

	first := actions(t, state, "a1")
	second := actions(t, state, "a1")

	want := []ActionKind{
		ActionAttack, ActionAttack,
		ActionMapAttack, ActionMapAttack,
		ActionSkillHeal,
		ActionReposition,
		ActionStandby,
	}
	if !reflect.DeepEqual(kinds(first), want) {
		t.Fatalf("actions: %+v", kinds(first))
	}
	if !reflect.DeepEqual(first, second) {
		t.Fatal("two calls gave two lists")
	}
}

func TestTheActionsOfAnUnknownUnitAreAnError(t *testing.T) {
	state := board(unit("a1", FactionAlly, Cell{0, 0}))

	if _, err := state.Actions("ghost"); err == nil {
		t.Fatal("the board holds no unit 'ghost'")
	}
}
