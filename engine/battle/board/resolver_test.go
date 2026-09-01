package board

import (
	"encoding/json"
	"errors"
	"os"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
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
					MapWeapons: []battle.MapWeapon{{Name: "missile"}},
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
				MapWeaponAmmo:           []int{3},
				Debuffs:                 []battle.Debuff{{Kind: "mobility", Magnitude: 0.2, AppliedPhase: 1}},
			},
			{
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
		{Faction: battle.FactionEnemy, Pos: battle.Cell{1, 1}, HP: 10,
			Pilot: battle.Pilot{SP: 60},
			Mech:  battle.Mech{HP: 9000, EN: 180}},
		{Faction: battle.FactionEnemy, Pos: battle.Cell{2, 1}, HP: 10,
			MaxHP: 7000, ENMax: 20, SPMax: 5,
			Pilot: battle.Pilot{SP: 60},
			Mech:  battle.Mech{HP: 9000, EN: 180}},
	}

	board, err := openingBoard(battle.Bounds{{0, 0}, {5, 4}}, "", nil, enemies)
	if err != nil {
		t.Fatal(err)
	}

	filled := &board.state.Units[0]
	if filled.MaxHP != 9000 || filled.ENMax != 180 || filled.SPMax != 60 {
		t.Fatalf("the pairing fills a maximum of zero: %+v", *filled)
	}
	stated := &board.state.Units[1]
	if stated.MaxHP != 7000 || stated.ENMax != 20 || stated.SPMax != 5 {
		t.Fatalf("an explicit maximum stands: %+v", *stated)
	}
}

func TestAUnitWithNoSizeCoversOneCell(t *testing.T) {
	wire := &battle.BattleState{
		Bounds: &battle.Bounds{{0, 0}, {4, 4}},
		Phase:  battle.FactionAlly,
		Units:  []battle.Unit{{Faction: battle.FactionAlly, HP: 1}},
	}

	board, err := restore(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if got := board.state.Units[0].Size; got != (battle.Cell{1, 1}) {
		t.Fatalf("size: %v", got)
	}
}

func TestInitBuildsTheBoardOfTheEnemiesAtTurnOne(t *testing.T) {
	board, err := openingBoard(battle.Bounds{{0, 0}, {5, 4}}, "ground",
		[]battle.TerrainCell{{Cell: battle.Cell{1, 1}, Terrain: "space"}},
		[]battle.Unit{{Faction: battle.FactionEnemy, Pos: battle.Cell{4, 4}, HP: 10}})
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
	if len(board.state.Units) != 1 || board.state.Units[0].Faction != battle.FactionEnemy {
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
			enemies: []battle.Unit{{Faction: battle.FactionEnemy,
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
	unit := &board.state.Units[0]
	unit.Value.MapWeaponAmmo[0] = 0
	*unit.Value.Skills[0].Amount = 1.0

	if wire.Units[0].MapWeaponAmmo[0] != 3 || *wire.Units[0].Skills[0].Amount != 3000.0 {
		t.Fatal("a write into the model reached the payload")
	}
}

func TestTheModelCopiesEveryFieldThatASystemWrites(t *testing.T) {
	wire := wireBoard()

	board, err := restore(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	unit := &board.state.Units[0]
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
		Trace:     engagement.Trace{{Kind: engagement.StrikeMain, ShooterID: 0, StruckID: 1, WeaponID: 2, Landed: true, Damage: 7, Killed: true}},
		Rotations: []turn.Rotation{{Turn: 1, Phase: battle.FactionEnemy}},
	})
	want := []any{
		battle.StrikeEvent{Event: "strike", Strike: "strike", ShooterID: 0, StruckID: 1, WeaponID: 2, Landed: true, Damage: 7, Killed: true},
		battle.PhaseEvent{Event: "phase", Turn: 1, Phase: battle.FactionEnemy},
	}
	if !reflect.DeepEqual(events, want) {
		t.Fatalf("events: %+v", events)
	}
}

func turnBoard(t *testing.T, phase battle.Faction, turnNumber int, units ...battle.Unit) *Board {
	t.Helper()
	bounds := battle.Bounds{{0, 0}, {5, 4}}
	candidate := battle.BattleState{
		Bounds: &bounds, Units: units, Phase: phase, Turn: turnNumber}
	if err := validate(&candidate); err != nil {
		t.Fatal(err)
	}
	return &Board{state: state.FromContract(candidate)}
}

func basicUnit(faction battle.Faction, x, y int) battle.Unit {
	return battle.Unit{
		Faction: faction,
		Pos:     battle.Cell{x, y}, Size: battle.Cell{1, 1},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140,
		Mech: battle.Mech{MoveRange: 1}, Pilot: battle.Pilot{},
	}
}

func armed(faction battle.Faction, x, y int) battle.Unit {
	out := basicUnit(faction, x, y)
	out.Mech.Weapons = []battle.Weapon{{Name: "gun", Power: 5000, RangeMin: 1, RangeMax: 3, Accuracy: 100, UsableAfterMove: true}}
	out.Mech.Attack, out.Mech.Defense = 4200, 3900
	out.Pilot.Ranged, out.Pilot.Melee, out.Pilot.Awaken = 220, 220, 220
	out.Pilot.Defense = 190
	out.Pilot.Reaction, out.Mech.Mobility = 205, 310
	return out
}

func idOf(value int) *int {
	return &value
}

func standby(id int) battle.Decision {
	return battle.Decision{UnitID: id, Kind: battle.ActionStandby}
}

func pendingOf(b *Board) []int {
	return turn.Pending(&b.state, b.state.Phase)
}

func targetsOf(b *Board, unitID int) []int {
	var out []int
	for index := range b.state.Units {
		other := &b.state.Units[index]
		if other.Faction == b.state.Units[unitID].Faction.Opposing() && other.Alive() {
			out = append(out, index)
		}
	}
	return out
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, basicUnit(battle.FactionAlly, 1, 1), basicUnit(battle.FactionEnemy, 4, 4))

	if _, err := board.act(standby(1), battle.NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.state.Phase != battle.FactionAlly || board.state.Units[0].Value.Acted {
		t.Fatal("the board changed on a refusal")
	}
}

func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, armed(battle.FactionAlly, 1, 1), armed(battle.FactionAlly, 1, 2), armed(battle.FactionEnemy, 2, 1))
	dice := battle.Forced{AttackerSupport: true, DefenderSupport: true, Strike: true, Counter: true}

	for acts := 0; len(turn.Gone(&board.state)) == 0; acts++ {
		if acts > 100 {
			t.Fatal("no side is gone after 100 activations")
		}
		actorID := pendingOf(board)[0]
		targets := targetsOf(board, actorID)
		action := standby(actorID)
		if len(targets) > 0 {
			action = battle.Decision{UnitID: actorID, Kind: battle.ActionAttack,
				TargetID: idOf(targets[0]), WeaponID: idOf(0),
				ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone}}
		}
		if _, err := board.act(action, dice); err != nil {
			t.Fatalf("act %d: %v", acts, err)
		}
	}
}
