package board

import (
	"encoding/json"
	"errors"
	"os"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func openingBoard(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, enemies []battle.Unit) (*Board, error) {
	out := New()
	if err := out.Load(bounds, terrain, terrainCells, enemies, battle.FactionAlly, 1); err != nil {
		return nil, err
	}
	return out, nil
}

func restore(state *battle.BattleState) (*Board, error) {
	if state == nil {
		return nil, errors.New("the payload carries no state")
	}
	if state.Bounds == nil {
		return nil, errors.New("the state carries no bounds")
	}
	out := New()
	if err := out.Load(*state.Bounds, state.Terrain, state.TerrainCells, state.Units,
		state.Phase, state.Turn); err != nil {
		return nil, err
	}
	return out, nil
}

func wireBoard() *battle.BattleState {
	kind := "mobility"
	amount := 3000.0
	bounds := battle.Bounds{{0, 0}, {9, 9}}
	return &battle.BattleState{
		Units: []battle.Unit{
			{
				ID:        "a1",
				Faction:   battle.FactionAlly,
				Pos:       battle.Cell{2, 3},
				Size:      battle.Cell{2, 3},
				HP:        8200,
				MaxHP:     9000,
				EN:        120,
				ENMax:     180,
				HasShield: true,
				Acted:     true,
				Skills: []battle.Skill{{
					Kind:            "skill_heal",
					Source:          battle.SourceMech,
					Amount:          &amount,
					Uses:            2,
					EndsActivation:  true,
					UsableAfterMove: true,
					Affects:         battle.AffectsAlly,
				}},
				SP:    30,
				SPMax: 45,
				Pilot: battle.Pilot{
					Ranged: 220, Melee: 180, Awaken: 240, Defense: 190, Reaction: 205, SP: 45,
				},
				Mech: battle.Mech{
					HP: 9000, EN: 180, Attack: 4100, Defense: 3900, Mobility: 310, MoveRange: 4,
					Weapons: []battle.Weapon{{
						Name:            "rifle",
						Power:           2400,
						RangeMin:        1,
						RangeMax:        4,
						ENCost:          15,
						Accuracy:        12,
						UsableAfterMove: true,
						DebuffKind:      &kind,
						DebuffMagnitude: 0.2,
						Categories:      []battle.WeaponCategory{battle.WeaponCategoryRanged},
					}},
				},
				SupportDefendCharges:    1,
				SupportDefendChargesMax: 1,
				SupportAttackCharges:    2,
				SupportDefendWhenAttack: true,
				Ammo:                    map[string]int{"missile": 3},
				Debuffs:                 []battle.Debuff{{Kind: "mobility", Magnitude: 0.2, AppliedPhase: 1}},
			},
			{
				ID:      "e1",
				Faction: battle.FactionEnemy,
				Pos:     battle.Cell{7, 7},
				Size:    battle.Cell{1, 1},
				HP:      5000,
			},
		},
		Phase:         battle.FactionAlly,
		Turn:          3,
		Bounds:        &bounds,
		PendingEvents: []string{"reinforcement"},
	}
}

func decodeFixtureState(t *testing.T) *Board {
	t.Helper()
	raw, err := os.ReadFile("../../../tests/fixtures/engine/debuff_ammo_board.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Setup struct {
			State battle.BattleState
		}
	}
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	board, err := restore(&fixture.Setup.State)
	if err != nil {
		t.Fatal(err)
	}
	return board
}

func TestInitFillsAMaximumThatThePayloadLeavesAtZero(t *testing.T) {
	enemies := []battle.Unit{
		{ID: "e1", Faction: battle.FactionEnemy, Pos: battle.Cell{1, 1}, HP: 10,
			Pilot: battle.Pilot{SP: 60},
			Mech:  battle.Mech{HP: 9000, EN: 180}},
		{ID: "e2", Faction: battle.FactionEnemy, Pos: battle.Cell{2, 1}, HP: 10,
			MaxHP: 7000, ENMax: 20, SPMax: 5,
			Pilot: battle.Pilot{SP: 60},
			Mech:  battle.Mech{HP: 9000, EN: 180}},
	}

	board, err := openingBoard(battle.Bounds{{0, 0}, {5, 4}}, "", nil, enemies)
	if err != nil {
		t.Fatal(err)
	}

	filled := board.state.Unit("e1")
	if filled.MaxHP != 9000 || filled.ENMax != 180 || filled.SPMax != 60 {
		t.Fatalf("the pairing fills a maximum of zero: %+v", *filled)
	}
	stated := board.state.Unit("e2")
	if stated.MaxHP != 7000 || stated.ENMax != 20 || stated.SPMax != 5 {
		t.Fatalf("an explicit maximum stands: %+v", *stated)
	}
}

func TestAUnitWithNoSizeCoversOneCell(t *testing.T) {
	wire := &battle.BattleState{
		Bounds: &battle.Bounds{{0, 0}, {4, 4}},
		Phase:  battle.FactionAlly,
		Units:  []battle.Unit{{ID: "a1", Faction: battle.FactionAlly, HP: 1}},
	}

	board, err := restore(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if got := board.state.Unit("a1").Size; got != (battle.Cell{1, 1}) {
		t.Fatalf("size: %v", got)
	}
}

func TestInitBuildsTheBoardOfTheEnemiesAtTurnOne(t *testing.T) {
	board, err := openingBoard(battle.Bounds{{0, 0}, {5, 4}}, "ground",
		[]battle.TerrainCell{{Cell: battle.Cell{1, 1}, Terrain: "space"}},
		[]battle.Unit{{ID: "e1", Faction: battle.FactionEnemy, Pos: battle.Cell{4, 4}, HP: 10}})
	if err != nil {
		t.Fatal(err)
	}
	if board.state.Turn != 1 || board.state.Phase != battle.FactionAlly {
		t.Fatalf("turn %d phase %s", board.state.Turn, board.state.Phase)
	}
	if board.state.Bounds != (battle.Bounds{{0, 0}, {5, 4}}) {
		t.Fatalf("bounds: %+v", board.state.Bounds)
	}
	if board.state.Terrain != battle.TerrainGround ||
		len(board.state.TerrainCells) != 1 || board.state.TerrainCells[0].Terrain != battle.TerrainSpace {
		t.Fatalf("terrain: %v %v", board.state.Terrain, board.state.TerrainCells)
	}
	if len(board.state.Units) != 1 || board.state.Units[0].ID != "e1" {
		t.Fatalf("units: %+v", board.state.Units)
	}
}

func TestInitRefusesAPayloadThatTheBoardCannotHold(t *testing.T) {
	bounds := battle.Bounds{{0, 0}, {2, 2}}
	cases := []struct {
		name         string
		terrainCells []battle.TerrainCell
		enemies      []battle.Unit
	}{
		{name: "a footprint outside the bounds",
			enemies: []battle.Unit{{ID: "x1", Faction: battle.FactionEnemy,
				Pos: battle.Cell{2, 2}, Size: battle.Cell{2, 2}, HP: 10}}},
		{name: "a terrain cell outside the bounds",
			terrainCells: []battle.TerrainCell{{Cell: battle.Cell{9, 9}, Terrain: "space"}}},
	}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			if _, err := openingBoard(bounds, "", one.terrainCells, one.enemies); err == nil {
				t.Fatal("the payload must fail")
			}
		})
	}
}

func TestTheDecodeKeepsWhatARuleReads(t *testing.T) {
	wire := wireBoard()

	board, err := restore(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	got := board.State()
	if !reflect.DeepEqual(got.Units[0], wire.Units[0]) {
		t.Fatalf("unit:\n%+v\n%+v", got.Units[0], wire.Units[0])
	}
	if got.Bounds == nil || *got.Bounds != (battle.Bounds{{0, 0}, {9, 9}}) {
		t.Fatalf("bounds: %+v", got.Bounds)
	}
	if got.Phase != battle.FactionAlly || got.Turn != 3 {
		t.Fatalf("phase %q, turn %d", got.Phase, got.Turn)
	}
}

func TestTheModelCopiesTheAmmoAndTheSkillAmount(t *testing.T) {
	wire := wireBoard()

	board, err := restore(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	unit := board.state.Unit("a1")
	unit.Value.Ammo["missile"] = 0
	*unit.Value.Skills[0].Amount = 1.0

	if wire.Units[0].Ammo["missile"] != 3 || *wire.Units[0].Skills[0].Amount != 3000.0 {
		t.Fatal("a write into the model reached the payload")
	}
}

func TestTheModelCopiesEveryFieldThatASystemWrites(t *testing.T) {
	wire := wireBoard()

	board, err := restore(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	unit := board.state.Unit("a1")
	unit.Value.HP, unit.Value.EN, unit.Value.SP = 0, 0, 0
	unit.Value.Pos, unit.Value.Acted = battle.Cell{9, 9}, false
	unit.Value.ChanceSteps = 7
	unit.Value.SupportDefendCharges, unit.Value.SupportAttackCharges = 0, 0
	unit.Value.Debuffs[0].Kind = "changed"

	payload := wire.Units[0]
	if payload.HP != 8200 || payload.EN != 120 || payload.SP != 30 ||
		payload.Pos != (battle.Cell{2, 3}) || !payload.Acted ||
		payload.ChanceSteps != 0 || payload.SupportDefendCharges != 1 ||
		payload.SupportAttackCharges != 2 || payload.Debuffs[0].Kind != "mobility" {
		t.Fatalf("a write into the model reached the payload: %+v", payload)
	}
}

func TestEncodeStateRoundTripsThroughLoad(t *testing.T) {
	first := decodeFixtureState(t)
	encoded := first.State()
	second, err := restore(&encoded)
	if err != nil {
		t.Fatal(err)
	}
	again := second.State()
	a, _ := json.Marshal(encoded)
	b, _ := json.Marshal(again)
	if string(a) != string(b) {
		t.Fatalf("the second encode differs:\n%s\n%s", a, b)
	}
	if encoded.Turn != first.state.Turn || encoded.Phase != first.state.Phase ||
		encoded.Bounds == nil {
		t.Fatalf("state: %+v", encoded)
	}
}

func TestTheResolutionEncodesStrikesThenRotations(t *testing.T) {
	events := eventsOf(resolution{
		Trace:     engagement.Trace{{Kind: engagement.StrikeMain, ShooterID: "a1", StruckID: "e1", Weapon: "gun", Landed: true, Damage: 7, Killed: true}},
		Rotations: []turn.Rotation{{Turn: 1, Phase: battle.FactionEnemy}},
	})
	want := []any{
		battle.StrikeEvent{Event: "strike", Strike: "strike", ShooterID: "a1", StruckID: "e1", Weapon: "gun", Landed: true, Damage: 7, Killed: true},
		battle.PhaseEvent{Event: "phase", Turn: 1, Phase: battle.FactionEnemy},
	}
	if !reflect.DeepEqual(events, want) {
		t.Fatalf("events: %+v", events)
	}
}
