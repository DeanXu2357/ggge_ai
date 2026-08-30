package board

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func wireBoard() *protocol.BattleState {
	kind := "mobility"
	amount := 3000.0
	bounds := protocol.Bounds{{0, 0}, {9, 9}}
	return &protocol.BattleState{
		Units: []protocol.Unit{
			{
				UnitID:    "a1",
				Faction:   protocol.FactionAlly,
				Pos:       protocol.Cell{2, 3},
				Size:      protocol.Cell{2, 3},
				HP:        8200,
				MaxHP:     9000,
				EN:        120,
				ENMax:     180,
				HasShield: true,
				Acted:     true,
				Skills: []protocol.Skill{{
					Kind:            "skill_heal",
					Source:          protocol.SourceMech,
					Amount:          &amount,
					Uses:            2,
					EndsActivation:  true,
					UsableAfterMove: true,
					RangeMax:        1,
					Blast:           1,
					Affects:         protocol.AffectsAlly,
				}},
				SP:    30,
				SPMax: 45,
				Pilot: protocol.Pilot{
					Ranged: 220, Melee: 180, Awaken: 240, Defense: 190, Reaction: 205, SP: 45,
				},
				Mech: protocol.Mech{
					HP: 9000, EN: 180, Attack: 4100, Defense: 3900, Mobility: 310, MoveRange: 4,
					Weapons: []protocol.Weapon{{
						Name:            "rifle",
						Power:           2400,
						RangeMin:        1,
						RangeMax:        4,
						ENCost:          15,
						Accuracy:        12,
						MapWeapon:       false,
						UsableAfterMove: true,
						DebuffKind:      &kind,
						DebuffMagnitude: 0.2,
						Categories:      []string{"ranged"},
					}},
				},
				SupportDefendCharges:    1,
				SupportDefendChargesMax: 1,
				SupportAttackCharges:    2,
				SupportDefendWhenAttack: true,
				Ammo:                    map[string]int{"missile": 3},
				Debuffs:                 []protocol.Debuff{{Kind: "mobility", Magnitude: 0.2, AppliedPhase: 1}},
			},
			{
				UnitID:  "e1",
				Faction: protocol.FactionEnemy,
				Pos:     protocol.Cell{7, 7},
				Size:    protocol.Cell{1, 1},
				HP:      5000,
			},
		},
		Phase:         protocol.FactionAlly,
		Turn:          3,
		Bounds:        &bounds,
		PendingEvents: []string{"reinforcement"},
	}
}

func TestTheDecodeKeepsWhatARuleReads(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	amount := 3000.0
	want := state.Unit{
		ID:        "a1",
		Faction:   state.FactionAlly,
		Footprint: state.Footprint{Anchor: state.Cell{2, 3}, Size: state.Size{2, 3}},
		HP:        8200,
		MaxHP:     9000,
		EN:        120,
		ENMax:     180,
		SP:        30,
		SPMax:     45,
		Pilot: &def.Pilot{
			Ranged: 220, Melee: 180, Awaken: 240, Defense: 190, Reaction: 205, SP: 45,
		},
		Acted:                   true,
		SupportDefendCharges:    1,
		SupportDefendChargesMax: 1,
		SupportAttackCharges:    2,
		HasShield:               true,
		SupportDefendWhenAttack: true,
		Ammo:                    map[string]int{"missile": 3},
		Debuffs:                 []state.Debuff{{Kind: "mobility", Magnitude: 0.2, AppliedPhase: 1}},
		Mech: &def.Mech{
			HP: 9000, EN: 180, Attack: 4100, Defense: 3900, Mobility: 310, MoveRange: 4,
			Weapons: []def.Weapon{{
				Name:            "rifle",
				Power:           2400,
				Range:           def.RadiusRange{Min: 1, Max: 4},
				ENCost:          15,
				Accuracy:        12,
				UsableAfterMove: true,
				DebuffKind:      "mobility",
				DebuffMagnitude: 0.2,
				Categories:      []def.WeaponCategory{def.WeaponCategoryRanged},
			}},
		},
		Skills: []state.Skill{{
			Kind:            "skill_heal",
			Source:          state.SourceMech,
			Amount:          &amount,
			Uses:            2,
			EndsActivation:  true,
			UsableAfterMove: true,
			Range:           def.RadiusRange{Min: 0, Max: 1},
			Blast:           1,
			Affects:         state.AffectsAlly,
		}},
	}
	if got := board.unit("a1"); !reflect.DeepEqual(*got, want) {
		t.Fatalf("unit:\n%+v\n%+v", *got, want)
	}
	if got := board.state.Bounds; got != (state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{9, 9}}) {
		t.Fatalf("bounds: %+v", got)
	}
	if board.state.Phase != state.FactionAlly || board.state.Turn != 3 {
		t.Fatalf("phase %q, turn %d", board.state.Phase, board.state.Turn)
	}
}

func TestTheModelCopiesTheAmmoAndTheSkillAmount(t *testing.T) {
	wire := wireBoard()

	board, err := DecodeState(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	unit := board.unit("a1")
	unit.Ammo["missile"] = 0
	*unit.Skills[0].Amount = 1.0

	if wire.Units[0].Ammo["missile"] != 3 || *wire.Units[0].Skills[0].Amount != 3000.0 {
		t.Fatal("a write into the model reached the payload")
	}
}

func TestAWeaponCategoryOutsideTheContractStopsTheDecode(t *testing.T) {
	wire := wireBoard()
	wire.Units[0].Mech.Weapons[0].Categories = []string{"psychic"}

	if _, err := DecodeState(wire); err == nil {
		t.Fatal("a category outside the contract must stop the decode")
	}
}

func TestInitFillsAMaximumThatThePayloadLeavesAtZero(t *testing.T) {
	request := protocol.InitRequest{
		Board: protocol.Board{Width: 6, Height: 5},
		Enemies: []protocol.Unit{
			{UnitID: "e1", Faction: protocol.FactionEnemy, Pos: protocol.Cell{1, 1}, HP: 10,
				Pilot: protocol.Pilot{SP: 60},
				Mech:  protocol.Mech{HP: 9000, EN: 180}},
			{UnitID: "e2", Faction: protocol.FactionEnemy, Pos: protocol.Cell{2, 1}, HP: 10,
				MaxHP: 7000, ENMax: 20, SPMax: 5,
				Pilot: protocol.Pilot{SP: 60},
				Mech:  protocol.Mech{HP: 9000, EN: 180}},
		},
	}

	board, err := DecodeInit(&request)
	if err != nil {
		t.Fatal(err)
	}

	filled := board.unit("e1")
	if filled.MaxHP != 9000 || filled.ENMax != 180 || filled.SPMax != 60 {
		t.Fatalf("the pairing fills a maximum of zero: %+v", *filled)
	}
	stated := board.unit("e2")
	if stated.MaxHP != 7000 || stated.ENMax != 20 || stated.SPMax != 5 {
		t.Fatalf("an explicit maximum stands: %+v", *stated)
	}
}

func TestTheModelSharesNoMemoryWithTheWireState(t *testing.T) {
	wire := wireBoard()

	board, err := DecodeState(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	board.unit("a1").Mech.Weapons[0].Name = "changed"

	if wire.Units[0].Mech.Weapons[0].Name != "rifle" {
		t.Fatal("a write into the model reached the payload")
	}
}

func TestAUnitWithNoSizeCoversOneCell(t *testing.T) {
	wire := &protocol.BattleState{
		Bounds: &protocol.Bounds{{0, 0}, {4, 4}},
		Phase:  protocol.FactionAlly,
		Units:  []protocol.Unit{{UnitID: "a1", Faction: protocol.FactionAlly, HP: 1}},
	}

	board, err := DecodeState(wire)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if got := board.unit("a1").Footprint.Size; got != (state.Size{1, 1}) {
		t.Fatalf("size: %v", got)
	}
}

func TestDecodeRefusesAPayloadOutsideTheContract(t *testing.T) {
	square := protocol.Bounds{{0, 0}, {4, 4}}
	ally := protocol.FactionAlly
	cases := map[string]*protocol.BattleState{
		"no state":  nil,
		"no bounds": {Phase: ally, Units: []protocol.Unit{{UnitID: "a1", Faction: ally}}},
		"no phase": {
			Bounds: &square,
			Units:  []protocol.Unit{{UnitID: "a1", Faction: ally}},
		},
		"an unknown faction": {
			Bounds: &square,
			Phase:  ally,
			Units:  []protocol.Unit{{UnitID: "a1", Faction: protocol.Faction("pirate")}},
		},
		"two units with one id": {
			Bounds: &square,
			Phase:  ally,
			Units: []protocol.Unit{
				{UnitID: "a1", Faction: ally},
				{UnitID: "a1", Faction: protocol.FactionEnemy},
			},
		},
		"a size below zero": {
			Bounds: &square,
			Phase:  ally,
			Units: []protocol.Unit{{
				UnitID:  "a1",
				Faction: ally,
				Size:    protocol.Cell{-1, 2},
			}},
		},
		"bounds that run backward": {
			Bounds: &protocol.Bounds{{4, 4}, {0, 0}},
			Phase:  ally,
		},
	}

	for name, wire := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := DecodeState(wire); err == nil {
				t.Fatal("the decode took a payload outside the contract")
			}
		})
	}
}

func TestAFootprintIsWithinTheBoardOnlyAsAWhole(t *testing.T) {
	bounds := state.Bounds{Low: state.Cell{0, 0}, High: state.Cell{4, 4}}

	if !(state.Footprint{Anchor: state.Cell{3, 3}, Size: state.Size{2, 2}}).Within(bounds) {
		t.Fatal("the anchor (3,3) holds a footprint of 2 by 2 on a board of 5 by 5")
	}
	if (state.Footprint{Anchor: state.Cell{4, 3}, Size: state.Size{2, 2}}).Within(bounds) {
		t.Fatal("an anchor on the last column puts half of the footprint outside")
	}
	if (state.Footprint{Anchor: state.Cell{-1, 0}, Size: state.Size{1, 1}}).Within(bounds) {
		t.Fatal("a cell below the low corner is outside")
	}
}

func TestAFootprintKnowsItsCells(t *testing.T) {
	footprint := state.Footprint{Anchor: state.Cell{1, 1}, Size: state.Size{2, 3}}

	want := []state.Cell{{1, 1}, {1, 2}, {1, 3}, {2, 1}, {2, 2}, {2, 3}}
	if got := footprint.Cells(); !reflect.DeepEqual(got, want) {
		t.Fatalf("cells: %v", got)
	}
}

func TestTheOpposingFactionOfEverySide(t *testing.T) {
	if state.FactionAlly.Opposing() != state.FactionEnemy {
		t.Fatal("the ally side fights the enemy side")
	}
	if state.FactionEnemy.Opposing() != state.FactionAlly ||
		state.FactionThirdParty.Opposing() != state.FactionAlly {
		t.Fatal("the enemy side and a third party fight the ally side")
	}
}

func TestTheCapabilityPayloadCarriesThePanelAndTheCells(t *testing.T) {
	amount := 2500.0
	ammo := 3
	unit := &state.Unit{
		ID:        "a1",
		Faction:   state.FactionAlly,
		Footprint: state.Footprint{Anchor: state.Cell{2, 3}, Size: state.Size{2, 1}},
		HP:        800,
		MaxHP:     1000,
		EN:        40,
		ENMax:     100,
		Mech: &def.Mech{
			MoveRange: 4,
			Weapons: []def.Weapon{
				{Name: "rifle", Range: def.RadiusRange{Min: 1, Max: 3}, ENCost: 10, Accuracy: 5,
					UsableAfterMove: true},
				{Name: "missile", Range: def.RadiusRange{Min: 2, Max: 5}, MapWeapon: true},
			},
		},
		Skills: []state.Skill{{Kind: "skill_heal", Amount: &amount, Uses: 2,
			Range: def.RadiusRange{Min: 0, Max: 2}, Blast: 1, Affects: state.AffectsAlly}},
		Ammo: map[string]int{"missile": ammo},
	}

	out := encodeCapabilities(capabilities{Unit: unit, MoveCells: []state.Cell{{2, 3}, {2, 4}}})

	if out.Unit.Pos != (protocol.Cell{2, 3}) || out.Unit.Size != (protocol.Cell{2, 1}) ||
		out.Unit.Faction != protocol.FactionAlly || out.Unit.MaxHP != 1000 {
		t.Fatalf("status: %+v", out.Unit)
	}
	if len(out.MoveCells) != 2 || out.MoveCells[1] != (protocol.Cell{2, 4}) {
		t.Fatalf("cells: %+v", out.MoveCells)
	}
	if out.Weapons[0].RangeMax != 3 || out.Weapons[0].Ammo != nil {
		t.Fatalf("rifle: %+v", out.Weapons[0])
	}
	if out.Weapons[1].Ammo == nil || *out.Weapons[1].Ammo != 3 || !out.Weapons[1].MapWeapon {
		t.Fatalf("missile: %+v", out.Weapons[1])
	}
	if out.Skills[0].Kind != "skill_heal" || *out.Skills[0].Amount != amount ||
		out.Skills[0].Uses != 2 || out.Skills[0].Blast != 1 ||
		out.Skills[0].Affects != protocol.AffectsAlly {
		t.Fatalf("skill: %+v", out.Skills[0])
	}
	if out.Error != nil {
		t.Fatalf("a unit that has not acted carries no error: %+v", out.Error)
	}
}

func TestTheCapabilityPayloadOfAnActedUnitCarriesTheState(t *testing.T) {
	unit := &state.Unit{ID: "a1", Faction: state.FactionAlly, HP: 100, Acted: true,
		Mech: &def.Mech{}}

	out := encodeCapabilities(capabilities{Unit: unit})

	if out.Error == nil || out.Error.Code != protocol.CodeAlreadyActed {
		t.Fatalf("error: %+v", out.Error)
	}
	if out.Weapons == nil || out.Skills == nil || out.MoveCells == nil {
		t.Fatalf("an empty list is a list, not a null: %+v", out)
	}
}

func TestTheEncodedSkillSharesNoMemoryWithTheModel(t *testing.T) {
	amount := 2500.0

	encoded := encodeSkills([]state.Skill{{Kind: "skill_heal", Amount: &amount}})
	amount = 0

	if *encoded[0].Amount != 2500.0 {
		t.Fatalf("skill: %+v", encoded[0])
	}
}

func TestTheEngagementPayloadCarriesTheOptionsOfTheTwoSides(t *testing.T) {
	defender := &state.Unit{ID: "d1", HP: 100}
	attacker := &state.Unit{ID: "e1", HP: 100}
	helper := &state.Unit{ID: "h1", HP: 100, Mech: &def.Mech{Weapons: []def.Weapon{{Name: "rifle"}}}}

	counter := engagement.Forecast{}
	encoded := encodeOptions(engagement.Options{
		Defender: engagement.SideOptions{Unit: defender,
			SupportDefenders: []engagement.SupportDefendOption{{Unit: helper}},
			SupportAttackers: []engagement.SupportAttackOption{{Unit: helper, Weapon: &helper.Mech.Weapons[0]}}},
		Attacker: engagement.SideOptions{Unit: attacker},
		ResponseAttacks: []engagement.ResponseAttackOption{
			{Stance: engagement.StanceDodge},
			{Stance: engagement.StanceCounter, Weapon: "saber", Counter: &counter},
			{Stance: engagement.StanceNone},
		},
	})

	if encoded.Defender.UnitID != "d1" || encoded.Attacker.UnitID != "e1" {
		t.Fatalf("sides: %+v", encoded)
	}
	if encoded.Defender.ResponseAttacks[0].Stance != protocol.StanceDodge ||
		encoded.Defender.ResponseAttacks[0].Weapon != nil ||
		encoded.Defender.ResponseAttacks[0].Counter != nil {
		t.Fatalf("dodge: %+v", encoded.Defender.ResponseAttacks[0])
	}
	if *encoded.Defender.ResponseAttacks[1].Weapon != "saber" ||
		encoded.Defender.ResponseAttacks[1].Counter == nil {
		t.Fatalf("a counter carries the forecast of its own strike: %+v",
			encoded.Defender.ResponseAttacks[1])
	}
	if encoded.Defender.ResponseAttacks[2].Stance != protocol.StanceNone {
		t.Fatalf("the stand: %+v", encoded.Defender.ResponseAttacks[2])
	}
	if encoded.Defender.SupportDefenders[0].UnitID != "h1" ||
		encoded.Defender.SupportAttackers[0].Weapon != "rifle" {
		t.Fatalf("the support units: %+v", encoded.Defender)
	}
	if encoded.Attacker.SupportDefenders == nil || encoded.Attacker.SupportAttackers == nil {
		t.Fatalf("an empty list is a list, not a null: %+v", encoded.Attacker)
	}
}

func TestTheEncodedForecastCarriesEveryNumberItHolds(t *testing.T) {
	rate := 0.75
	damage := 2400
	kill := true

	full := encodeForecast(engagement.Forecast{HitRate: &rate, Damage: &damage, Kill: &kill})
	lean := encodeForecast(engagement.Forecast{Damage: &damage})

	if *full.HitRate != 0.75 || *full.Damage != 2400 || !*full.Kill {
		t.Fatalf("forecast: %+v", full)
	}
	if lean.HitRate != nil || lean.Kill != nil || *lean.Damage != 2400 {
		t.Fatalf("a field that the engine cannot answer stays null: %+v", lean)
	}
	rate, damage, kill = 0, 0, false
	if *full.HitRate != 0.75 || *full.Damage != 2400 || !*full.Kill {
		t.Fatalf("the encode shares no memory with the model: %+v", full)
	}
}

func TestTheDecodedActionCarriesTheFieldsOfTheEngagement(t *testing.T) {
	moveTo := protocol.Cell{4, 5}
	name := "rifle"
	target := "e1"

	action, err := DecodeDecision(&protocol.Decision{
		UnitID: "a1", Kind: protocol.ActionAttack, MoveTo: &moveTo,
		TargetID: &target, Weapon: &name,
	})

	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if action.Kind != engagement.ActionAttack || *action.MoveTo != (state.Cell{4, 5}) ||
		action.Weapon != "rifle" || action.TargetID != "e1" {
		t.Fatalf("action: %+v", action)
	}
	lean, err := DecodeDecision(&protocol.Decision{UnitID: "a1", Kind: protocol.ActionStandby})
	if err != nil || lean.MoveTo != nil || lean.Weapon != "" {
		t.Fatalf("a field with no value stays empty: %+v, %v", lean, err)
	}
}

func TestTheBoardAnswersByUnitIdentity(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	unit := board.unit("a1")
	if unit == nil || !alive(unit) {
		t.Fatalf("unit: %v", unit)
	}
	if board.unit("ghost") != nil {
		t.Fatal("the board holds no unit 'ghost'")
	}

	unit.HP = 0

	if alive(unit) || alive(board.unit("ghost")) {
		t.Fatal("a unit with no hit points is not alive, and neither is a unit that is not there")
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
			State protocol.BattleState
		}
	}
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	board, err := DecodeState(&fixture.Setup.State)
	if err != nil {
		t.Fatal(err)
	}
	return board
}

func TestInitBuildsTheBoardOfTheEnemiesAtTurnOne(t *testing.T) {
	request := protocol.InitRequest{
		Board:   protocol.Board{Width: 6, Height: 5, Terrain: "ground", TerrainCells: []protocol.TerrainCell{{Cell: protocol.Cell{1, 1}, Terrain: "space"}}},
		Enemies: []protocol.Unit{{UnitID: "e1", Faction: protocol.FactionEnemy, Pos: protocol.Cell{4, 4}, HP: 10}},
		Seed:    9,
	}

	board, err := DecodeInit(&request)
	if err != nil {
		t.Fatal(err)
	}
	if board.state.Turn != 1 || board.state.Phase != state.FactionAlly {
		t.Fatalf("turn %d phase %s", board.state.Turn, board.state.Phase)
	}
	if board.state.Bounds != (state.Bounds{High: state.Cell{5, 4}}) {
		t.Fatalf("bounds: %+v", board.state.Bounds)
	}
	if board.state.DefaultTerrain != state.TerrainGround ||
		board.state.TerrainCells[state.Cell{1, 1}] != state.TerrainSpace {
		t.Fatalf("terrain: %v %v", board.state.DefaultTerrain, board.state.TerrainCells)
	}
	if len(board.state.Units) != 1 || board.state.Units[0].ID != "e1" {
		t.Fatalf("units: %+v", board.state.Units)
	}
}

func TestInitRefusesABoardWithNoCell(t *testing.T) {
	if _, err := DecodeInit(&protocol.InitRequest{Board: protocol.Board{Width: 0, Height: 5}}); err == nil {
		t.Fatal("a width of 0 must fail")
	}
}

func TestInitRefusesAPayloadThatTheBoardCannotHold(t *testing.T) {
	board := protocol.Board{Width: 3, Height: 3}
	cases := []struct {
		name    string
		request protocol.InitRequest
	}{
		{"a unit of 'enemies' that is no enemy", protocol.InitRequest{Board: board,
			Enemies: []protocol.Unit{{UnitID: "x1", Faction: protocol.FactionAlly,
				Pos: protocol.Cell{1, 1}, HP: 10}}}},
		{"a footprint outside the bounds", protocol.InitRequest{Board: board,
			Enemies: []protocol.Unit{{UnitID: "x1", Faction: protocol.FactionEnemy,
				Pos: protocol.Cell{2, 2}, Size: protocol.Cell{2, 2}, HP: 10}}}},
		{"a terrain cell outside the bounds", protocol.InitRequest{
			Board: protocol.Board{Width: 3, Height: 3,
				TerrainCells: []protocol.TerrainCell{{Cell: protocol.Cell{9, 9}, Terrain: "space"}}}}},
	}

	for _, one := range cases {
		t.Run(one.name, func(t *testing.T) {
			if _, err := DecodeInit(&one.request); err == nil {
				t.Fatal("the payload must fail")
			}
		})
	}
}

func TestEncodeStateRoundTripsThroughDecodeState(t *testing.T) {
	first := decodeFixtureState(t)
	encoded := first.State()
	second, err := DecodeState(&encoded)
	if err != nil {
		t.Fatal(err)
	}
	again := second.State()
	a, _ := json.Marshal(encoded)
	b, _ := json.Marshal(again)
	if string(a) != string(b) {
		t.Fatalf("the second encode differs:\n%s\n%s", a, b)
	}
	if encoded.Turn != first.state.Turn || encoded.Phase != wireFactions[first.state.Phase] ||
		encoded.Bounds == nil {
		t.Fatalf("state: %+v", encoded)
	}
}

func TestTheResolutionEncodesStrikesThenRotations(t *testing.T) {
	events := encodeResolution(resolution{
		Trace:     engagement.Trace{{Kind: engagement.StrikeMain, ShooterID: "a1", StruckID: "e1", Weapon: "gun", Landed: true, Damage: 7, Killed: true}},
		Rotations: []turn.Rotation{{Turn: 1, Phase: state.FactionEnemy}},
	})
	want := []any{
		protocol.StrikeEvent{Event: "strike", Strike: "strike", ShooterID: "a1", StruckID: "e1", Weapon: "gun", Landed: true, Damage: 7, Killed: true},
		protocol.PhaseEvent{Event: "phase", Turn: 1, Phase: protocol.FactionEnemy},
	}
	if !reflect.DeepEqual(events, want) {
		t.Fatalf("events: %+v", events)
	}
}

func TestTheSummaryNamesThePendingUnitsAndTheGoneSides(t *testing.T) {
	board := decodeFixtureState(t)
	board.state.Phase = state.FactionAlly
	for index := range board.state.Units {
		if board.state.Units[index].Faction == state.FactionEnemy {
			board.state.Units[index].HP = 0
		}
	}
	summary := board.Summary()
	if summary.Turn != board.state.Turn || summary.Phase != wireFactions[board.state.Phase] {
		t.Fatalf("summary: %+v", summary)
	}
	if !reflect.DeepEqual(summary.Gone, []protocol.Faction{protocol.FactionEnemy}) {
		t.Fatalf("gone: %v", summary.Gone)
	}
	if len(summary.Pending) == 0 {
		t.Fatal("the pending list must name the ally units that did not act")
	}
}
