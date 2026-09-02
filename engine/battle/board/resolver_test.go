package board

import (
	"encoding/json"
	"errors"
	"os"
	"reflect"
	"slices"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
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

	filled := &board.content.Units[0]
	if filled.MaxHP != 9000 || filled.ENMax != 180 || filled.SPMax != 60 {
		t.Fatalf("the pairing fills a maximum of zero: %+v", *filled)
	}
	stated := &board.content.Units[1]
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

	if got := board.content.Units[0].Size; got != (battle.Cell{1, 1}) {
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
	if board.values.Turn != 1 || board.values.Phase != battle.FactionAlly {
		t.Fatalf("turn %d phase %s", board.values.Turn, board.values.Phase)
	}
	if board.content.Bounds != (battle.Bounds{{0, 0}, {5, 4}}) {
		t.Fatalf("bounds: %+v", board.content.Bounds)
	}
	if board.content.Terrain != battle.TerrainGround ||
		len(board.content.TerrainCells) != 1 ||
		board.content.TerrainCells[0].Terrain != battle.TerrainSpace {
		t.Fatalf("terrain: %v %v", board.content.Terrain, board.content.TerrainCells)
	}
	if len(board.content.Units) != 1 || board.content.Units[0].Faction != battle.FactionEnemy {
		t.Fatalf("units: %+v", board.content.Units)
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
	unit := &board.values.Units[0]
	unit.MapWeaponAmmo[0] = 0
	*unit.Skills[0].Amount = 1.0

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
	unit := &board.values.Units[0]
	unit.HP, unit.EN, unit.SP = 0, 0, 0
	unit.Pos, unit.Acted = battle.Cell{9, 9}, false
	unit.ChanceSteps = 7
	unit.SupportDefendCharges, unit.SupportAttackCharges = 0, 0
	unit.Debuffs[0].Kind = "changed"

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
	if encoded.Turn != first.values.Turn || encoded.Phase != first.values.Phase ||
		encoded.Bounds == nil {
		t.Fatalf("state: %+v", encoded)
	}
}

func TestTheResultOfAnActCarriesTheStrikesAndTheRotations(t *testing.T) {
	survivor := armed(battle.FactionEnemy, 2, 1)
	survivor.HP, survivor.MaxHP = 99000, 99000
	board := turnBoard(t, battle.FactionAlly, 1, armed(battle.FactionAlly, 1, 1), survivor)
	action := battle.Decision{UnitID: 0, Kind: battle.ActionAttack,
		TargetID: idOf(1), WeaponID: idOf(0),
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone}}

	result, err := board.Act(&action, battle.Forced{Strike: true})
	if err != nil {
		t.Fatal(err)
	}

	if len(result.Strikes) != 1 {
		t.Fatalf("strikes: %+v", result.Strikes)
	}
	strike := result.Strikes[0]
	if strike.Event != "strike" || strike.Strike != "strike" ||
		strike.ShooterID != 0 || strike.StruckID != 1 || !strike.Landed || strike.Damage <= 0 {
		t.Fatalf("strike: %+v", strike)
	}
	want := []battle.PhaseEvent{
		{Event: "phase", Turn: 1, Phase: battle.FactionThirdParty},
		{Event: "phase", Turn: 1, Phase: battle.FactionEnemy},
	}
	if !reflect.DeepEqual(result.Rotations, want) {
		t.Fatalf("rotations: %+v", result.Rotations)
	}
}

func TestAnActLeavesTheContentColumnAsItWas(t *testing.T) {
	survivor := armed(battle.FactionEnemy, 2, 1)
	survivor.HP, survivor.MaxHP = 99000, 99000
	board := turnBoard(t, battle.FactionAlly, 1, armed(battle.FactionAlly, 1, 1), survivor)
	action := battle.Decision{UnitID: 0, Kind: battle.ActionAttack,
		TargetID: idOf(1), WeaponID: idOf(0),
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0)}}
	before, _ := state.FromContract(board.State())
	definitions := slices.Clone(board.content.Units)

	result, err := board.Act(&action, battle.Forced{Strike: true, Counter: true})
	if err != nil {
		t.Fatal(err)
	}

	if len(result.Strikes) == 0 || !result.Strikes[0].Landed {
		t.Fatalf("the case must land a strike: %+v", result.Strikes)
	}
	after, _ := state.FromContract(board.State())
	if !reflect.DeepEqual(before, after) {
		t.Fatalf("the act wrote the content column:\n%+v\n%+v", before, after)
	}
	for index := range board.content.Units {
		if board.content.Units[index].Mech != definitions[index].Mech ||
			board.content.Units[index].Pilot != definitions[index].Pilot {
			t.Errorf("the act gave unit %d another mech or another pilot", index)
		}
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
	content, values := state.FromContract(candidate)
	return &Board{content: content, values: values}
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
	view := b.view()
	return turn.Pending(view, view.Values.Phase)
}

func targetsOf(b *Board, unitID int) []int {
	var out []int
	for index := range b.content.Units {
		if b.content.Units[index].Faction == b.content.Units[unitID].Faction.Opposing() &&
			b.values.Units[index].HP > 0 {
			out = append(out, index)
		}
	}
	return out
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, basicUnit(battle.FactionAlly, 1, 1), basicUnit(battle.FactionEnemy, 4, 4))

	refused := standby(1)
	if _, err := board.Act(&refused, battle.NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.values.Phase != battle.FactionAlly || board.values.Units[0].Acted {
		t.Fatal("the board changed on a refusal")
	}
}

func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, battle.FactionAlly, 1, armed(battle.FactionAlly, 1, 1), armed(battle.FactionAlly, 1, 2), armed(battle.FactionEnemy, 2, 1))
	dice := battle.Forced{AttackerSupport: true, DefenderSupport: true, Strike: true, Counter: true}

	for acts := 0; len(goneOf(board)) == 0; acts++ {
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
		if _, err := board.Act(&action, dice); err != nil {
			t.Fatalf("act %d: %v", acts, err)
		}
	}
}

func goneOf(b *Board) []battle.Faction {
	return turn.Gone(b.view())
}
