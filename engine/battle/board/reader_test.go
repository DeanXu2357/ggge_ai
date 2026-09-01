package board

import (
	"errors"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func rifle(name string, rangeMin, rangeMax int) battle.Weapon {
	return battle.Weapon{Name: name, RangeMin: rangeMin, RangeMax: rangeMax, UsableAfterMove: true}
}

func mustActions(t *testing.T, b *Board, id int) battle.ActionsResponse {
	t.Helper()
	out, err := b.Actions(id)
	if err != nil {
		t.Fatalf("actions: %v", err)
	}
	return out
}

func TestTheActionsCarryTheCellsTheUnitReaches(t *testing.T) {
	b := board(unitAt(battle.FactionAlly, battle.Cell{0, 0}),
		unitAt(battle.FactionEnemy, battle.Cell{1, 0}))
	b.state.Units[0].Mech.MoveRange = 1

	out := mustActions(t, b, 0)

	want := []battle.Cell{{0, 0}, {0, 1}}
	if !reflect.DeepEqual(out.MoveCells, want) {
		t.Fatalf("the foe blocks the cell (1,0): %v", out.MoveCells)
	}
	if out.Unit.UnitID != 0 {
		t.Fatalf("unit: %v", out.Unit)
	}
}

// The command reads no resource and no band: a weapon with no energy left, a
// weapon that reaches nothing and a skill with no room all stay in the answer.
func TestTheActionsJudgeNoResourceAndNoBand(t *testing.T) {
	costly := rifle("costly", 1, 1)
	costly.ENCost = 20
	ally := unitAt(battle.FactionAlly, battle.Cell{0, 0})
	ally.EN = 0
	ally.MaxHP = ally.HP
	ally.Mech.Weapons = []battle.Weapon{costly}
	ally.Skills = []battle.Skill{{Kind: "skill_heal", Uses: 1}}
	b := board(ally, unitAt(battle.FactionEnemy, battle.Cell{4, 4}))

	out := mustActions(t, b, 0)

	if len(out.Weapons) != 1 || len(out.Skills) != 1 {
		t.Fatalf("the answer holds the whole panel: %+v", out)
	}
}

func TestTheActionsOfAUnitThatCannotAnswerAreAnError(t *testing.T) {
	dead := unitAt(battle.FactionAlly, battle.Cell{0, 1})
	dead.HP = 0
	b := board(unitAt(battle.FactionAlly, battle.Cell{0, 0}),
		unitAt(battle.FactionEnemy, battle.Cell{2, 0}), dead)
	cases := map[string]struct {
		unitID int
		want   error
	}{
		"an unknown unit":      {9, battle.ErrNoUnit},
		"a destroyed unit":     {2, battle.ErrDestroyed},
		"a unit off the phase": {1, battle.ErrOffPhase},
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

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	amount := 0.5
	bounds := battle.Bounds{{0, 0}, {4, 4}}
	b := &Board{state: state.FromContract(battle.BattleState{
		Bounds: &bounds,
		Phase:  battle.FactionAlly,
		Units: []battle.Unit{{
			Faction: battle.FactionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
			MapWeaponAmmo: []int{3},
			Debuffs:       []battle.Debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
			Skills:        []battle.Skill{{Kind: "boost", Amount: &amount, Uses: 1}},
			Mech:          battle.Mech{MapWeapons: []battle.MapWeapon{{Name: "w"}}},
		}},
		TerrainCells: []battle.TerrainCell{{Cell: battle.Cell{1, 1}, Terrain: battle.TerrainGround}},
	})}

	clone := b.State()
	clone.Units[0].HP = 1
	clone.Units[0].MapWeaponAmmo[0] = 0
	clone.Units[0].Debuffs[0].Kind = "changed"
	*clone.Units[0].Skills[0].Amount = 9
	clone.Units[0].Skills[0].Uses = 2
	clone.TerrainCells[0].Terrain = battle.TerrainSpace
	clone.Phase = battle.FactionEnemy

	unit := b.state.Units[0]
	if unit.Value.HP != 10 || unit.Value.MapWeaponAmmo[0] != 3 || unit.Value.Debuffs[0].Kind != "defense" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if *unit.Value.Skills[0].Amount != 0.5 || unit.Value.Skills[0].Uses != 1 {
		t.Fatalf("the board skill changed with the clone: %+v", unit.Value.Skills[0])
	}
	if b.state.TerrainCells[0].Terrain != battle.TerrainGround || b.state.Phase != battle.FactionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}

func TestTheActionsPayloadCarriesThePanelAndTheCells(t *testing.T) {
	amount := 2500.0
	ammo := 3
	unit := &state.Unit{
		Faction: battle.FactionAlly,
		Size:    battle.Cell{2, 1},
		MaxHP:   1000,
		ENMax:   100,
		Mech: &def.Mech{
			MoveRange: 4,
			Weapons: []def.Weapon{
				{Name: "rifle", RangeMin: 1, RangeMax: 3, ENCost: 10, Accuracy: 5,
					UsableAfterMove: true},
			},
			MapWeapons: []def.MapWeapon{
				{Name: "missile",
					Affects: battle.MapWeaponAffectsEnemy,
					AffectArea: def.AffectArea{
						ApplyShape: def.ShapeRange{Cells: []battle.Cell{{0, 0}, {1, 0}},
							Direction: battle.DirectionUp},
						EffectShape: def.ShapeRange{Cells: []battle.Cell{{0, 5}},
							Direction: battle.DirectionNone}}},
			},
		},
		Value: state.UnitValue{
			Pos: battle.Cell{2, 3},
			HP:  800,
			EN:  40,
			Skills: []def.Skill{{Kind: "skill_heal", Amount: &amount, Uses: 2,
				Affects: battle.AffectsAlly}},
			MapWeaponAmmo: []int{ammo},
		},
	}

	out := actionsOf(4, unit, []battle.Cell{{2, 3}, {2, 4}})

	if out.Unit.UnitID != 4 || out.Unit.Pos != (battle.Cell{2, 3}) ||
		out.Unit.Size != (battle.Cell{2, 1}) ||
		out.Unit.Faction != battle.FactionAlly || out.Unit.MaxHP != 1000 {
		t.Fatalf("status: %+v", out.Unit)
	}
	if len(out.MoveCells) != 2 || out.MoveCells[1] != (battle.Cell{2, 4}) {
		t.Fatalf("cells: %+v", out.MoveCells)
	}
	if len(out.Weapons) != 1 || out.Weapons[0].RangeMax != 3 {
		t.Fatalf("rifle: %+v", out.Weapons)
	}
	area := out.MapWeapons[0]
	if area.Ammo != 3 || len(area.EffectShape.Cells) != 1 ||
		area.Affects != battle.MapWeaponAffectsEnemy ||
		area.ApplyShape.Direction != battle.DirectionUp || len(area.ApplyShape.Cells) != 2 {
		t.Fatalf("missile: %+v", area)
	}
	if out.Skills[0].Kind != "skill_heal" || *out.Skills[0].Amount != amount ||
		out.Skills[0].Uses != 2 || out.Skills[0].Affects != battle.AffectsAlly {
		t.Fatalf("skill: %+v", out.Skills[0])
	}
	if out.Weapons == nil || out.MapWeapons == nil || out.Skills == nil || out.MoveCells == nil {
		t.Fatalf("an empty list is a list, not a null: %+v", out)
	}
}

func TestTheActionsOfAnActedUnitAreARefusal(t *testing.T) {
	b := board(unitAt(battle.FactionAlly, battle.Cell{0, 0}))
	b.state.Units[0].Value.Acted = true

	_, err := b.Actions(0)

	if !errors.Is(err, battle.ErrActed) {
		t.Fatalf("error: %v", err)
	}
}

func TestTheSummaryNamesThePendingUnitsAndTheGoneSides(t *testing.T) {
	board := decodeFixtureState(t)
	board.state.Phase = battle.FactionAlly
	for index := range board.state.Units {
		if board.state.Units[index].Faction == battle.FactionEnemy {
			board.state.Units[index].Value.HP = 0
		}
	}
	summary := board.Summary()
	if summary.Turn != board.state.Turn || summary.Phase != board.state.Phase {
		t.Fatalf("summary: %+v", summary)
	}
	if !reflect.DeepEqual(summary.Gone, []battle.Faction{battle.FactionEnemy}) {
		t.Fatalf("gone: %v", summary.Gone)
	}
	if len(summary.PendingIDs) == 0 {
		t.Fatal("the pending list must name the ally units that did not act")
	}
}

func TestTheBoardAnswersByUnitIdentity(t *testing.T) {
	board, err := restore(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	unit, err := board.state.UnitAt(0)
	if err != nil || !unit.Alive() {
		t.Fatalf("unit: %v, error: %v", unit, err)
	}
	ghost, err := board.state.UnitAt(len(board.state.Units))
	if ghost != nil || !errors.Is(err, battle.ErrNoUnit) {
		t.Fatalf("a position outside the slice: %v, error: %v", ghost, err)
	}

	unit.Value.HP = 0

	if unit.Alive() || ghost.Alive() {
		t.Fatal("a unit with no hit points is not alive, and neither is a unit that is not there")
	}
}
