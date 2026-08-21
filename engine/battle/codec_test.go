package battle

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func wireBoard() *protocol.BattleState {
	kind := "mobility"
	bounds := protocol.Bounds{{0, 0}, {9, 9}}
	return &protocol.BattleState{
		Units: []protocol.Unit{
			{
				UnitID:                  "a1",
				Faction:                 protocol.FactionAlly,
				Pos:                     protocol.Cell{2, 3},
				Size:                    protocol.Cell{2, 3},
				HP:                      8200,
				MaxHP:                   9000,
				EN:                      120,
				ENMax:                   180,
				UnitAttack:              4100,
				UnitDefense:             3900,
				PilotAttack:             220,
				PilotDefense:            190,
				Reaction:                205,
				Mobility:                310,
				MoveRange:               4,
				SupportDefendCharges:    1,
				SupportDefendChargesMax: 1,
				SupportAttackCharges:    2,
				AttackShield:            true,
				Ammo:                    map[string]int{"missile": 3},
				Weapons: []protocol.Weapon{{
					Name:            "rifle",
					Power:           2400,
					RangeMin:        1,
					RangeMax:        4,
					ENCost:          15,
					Accuracy:        12,
					MapWeapon:       false,
					Blast:           1,
					DebuffKind:      &kind,
					DebuffMagnitude: 0.2,
				}},
				Debuffs: []protocol.Debuff{{Kind: "mobility", Magnitude: 0.2, AppliedPhase: 1}},
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

	want := Unit{
		ID:                   "a1",
		Faction:              FactionAlly,
		Footprint:            Footprint{Anchor: Cell{2, 3}, Size: Size{2, 3}},
		HP:                   8200,
		EN:                   120,
		Pilot:                Pilot{Attack: 220, Defense: 190, Reaction: 205},
		Mech:                 Mech{Attack: 4100, Defense: 3900, Mobility: 310},
		MoveRange:            4,
		SupportDefendCharges: 1,
		SupportAttackCharges: 2,
		Weapons: []Weapon{{
			Name:   "rifle",
			Range:  RadiusRange{Min: 1, Max: 4},
			ENCost: 15,
		}},
	}
	if got := board.Unit("a1"); !reflect.DeepEqual(*got, want) {
		t.Fatalf("unit:\n%+v\n%+v", *got, want)
	}
	if got := board.Bounds; got != (Bounds{Low: Cell{0, 0}, High: Cell{9, 9}}) {
		t.Fatalf("bounds: %+v", got)
	}
}

func TestAPayloadWithNoMechBaseLeavesTheBaseEmpty(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	unit := board.Unit("a1")
	if unit.HP != 8200 || unit.EN != 120 || unit.MoveRange != 4 || len(unit.Weapons) != 1 {
		t.Fatalf("the final panel: %+v", *unit)
	}
	if want := (Mech{Attack: 4100, Defense: 3900, Mobility: 310}); !reflect.DeepEqual(unit.Mech, want) {
		t.Fatalf("the base of the mech: %+v", unit.Mech)
	}
}

func TestTheMechBaseOfThePayloadReachesTheMechAlone(t *testing.T) {
	state := wireBoard()
	state.Units[0].MechHP = 9000
	state.Units[0].MechEN = 180
	state.Units[0].MechMoveRange = 3
	state.Units[0].MechWeapons = []protocol.Weapon{
		{Name: "beam", RangeMin: 1, RangeMax: 2, ENCost: 20},
	}

	board, err := DecodeState(state)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	unit := board.Unit("a1")
	want := Mech{
		Attack: 4100, Defense: 3900, Mobility: 310,
		HP: 9000, EN: 180, MoveRange: 3,
		Weapons: []Weapon{{Name: "beam", Range: RadiusRange{Min: 1, Max: 2}, ENCost: 20}},
	}
	if !reflect.DeepEqual(unit.Mech, want) {
		t.Fatalf("the base of the mech:\n%+v\n%+v", unit.Mech, want)
	}
	if unit.HP != 8200 || unit.EN != 120 || unit.MoveRange != 4 {
		t.Fatalf("the final panel: %+v", *unit)
	}
	if len(unit.Weapons) != 1 || unit.Weapons[0].Name != "rifle" {
		t.Fatalf("the weapons of the final panel: %v", unit.Weapons)
	}
}

func TestTheFinalPanelAndTheMechBaseMoveApart(t *testing.T) {
	state := wireBoard()
	state.Units[0].MechHP = 9000
	state.Units[0].MechWeapons = []protocol.Weapon{{Name: "rifle"}}

	board, err := DecodeState(state)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	unit := board.Unit("a1")
	unit.HP = 1
	unit.Weapons[0].Name = "changed"

	if unit.Mech.HP != 9000 || unit.Mech.Weapons[0].Name != "rifle" {
		t.Fatalf("a write into the final panel reached the mech: %+v", unit.Mech)
	}
}

func TestTheModelSharesNoMemoryWithTheWireState(t *testing.T) {
	state := wireBoard()

	board, err := DecodeState(state)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	board.Unit("a1").Weapons[0].Name = "changed"

	if state.Units[0].Weapons[0].Name != "rifle" {
		t.Fatal("a write into the model reached the payload")
	}
}

func TestAUnitWithNoSizeCoversOneCell(t *testing.T) {
	state := &protocol.BattleState{
		Bounds: &protocol.Bounds{{0, 0}, {4, 4}},
		Units:  []protocol.Unit{{UnitID: "a1", Faction: protocol.FactionAlly, HP: 1}},
	}

	board, err := DecodeState(state)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if got := board.Unit("a1").Footprint.Size; got != (Size{1, 1}) {
		t.Fatalf("size: %v", got)
	}
}

func TestDecodeRefusesAPayloadOutsideTheContract(t *testing.T) {
	square := protocol.Bounds{{0, 0}, {4, 4}}
	cases := map[string]*protocol.BattleState{
		"no state":  nil,
		"no bounds": {Units: []protocol.Unit{{UnitID: "a1", Faction: protocol.FactionAlly}}},
		"an unknown faction": {
			Bounds: &square,
			Units:  []protocol.Unit{{UnitID: "a1", Faction: protocol.Faction("pirate")}},
		},
		"two units with one id": {
			Bounds: &square,
			Units: []protocol.Unit{
				{UnitID: "a1", Faction: protocol.FactionAlly},
				{UnitID: "a1", Faction: protocol.FactionEnemy},
			},
		},
		"a size below zero": {
			Bounds: &square,
			Units: []protocol.Unit{{
				UnitID:  "a1",
				Faction: protocol.FactionAlly,
				Size:    protocol.Cell{-1, 2},
			}},
		},
		"bounds that run backward": {
			Bounds: &protocol.Bounds{{4, 4}, {0, 0}},
		},
	}

	for name, state := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := DecodeState(state); err == nil {
				t.Fatal("the decode took a payload outside the contract")
			}
		})
	}
}

func TestAFootprintIsWithinTheBoardOnlyAsAWhole(t *testing.T) {
	bounds := Bounds{Low: Cell{0, 0}, High: Cell{4, 4}}

	if !(Footprint{Anchor: Cell{3, 3}, Size: Size{2, 2}}).Within(bounds) {
		t.Fatal("the anchor (3,3) holds a footprint of 2 by 2 on a board of 5 by 5")
	}
	if (Footprint{Anchor: Cell{4, 3}, Size: Size{2, 2}}).Within(bounds) {
		t.Fatal("an anchor on the last column puts half of the footprint outside")
	}
	if (Footprint{Anchor: Cell{-1, 0}, Size: Size{1, 1}}).Within(bounds) {
		t.Fatal("a cell below the low corner is outside")
	}
}

func TestAFootprintKnowsItsCells(t *testing.T) {
	footprint := Footprint{Anchor: Cell{1, 1}, Size: Size{2, 3}}

	want := []Cell{{1, 1}, {1, 2}, {1, 3}, {2, 1}, {2, 2}, {2, 3}}
	if got := footprint.Cells(); !reflect.DeepEqual(got, want) {
		t.Fatalf("cells: %v", got)
	}
}

func TestTheOpposingFactionOfEverySide(t *testing.T) {
	if FactionAlly.Opposing() != FactionEnemy {
		t.Fatal("the ally side fights the enemy side")
	}
	if FactionEnemy.Opposing() != FactionAlly || FactionThirdParty.Opposing() != FactionAlly {
		t.Fatal("the enemy side and a third party fight the ally side")
	}
}

func TestTheBoardAnswersByUnitIdentity(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	unit := board.Unit("a1")
	if unit == nil || !unit.Alive() {
		t.Fatalf("unit: %v", unit)
	}
	if board.Unit("ghost") != nil {
		t.Fatal("the board holds no unit 'ghost'")
	}

	unit.HP = 0

	if unit.Alive() || board.Unit("ghost").Alive() {
		t.Fatal("a unit with no hit points is not alive, and neither is a unit that is not there")
	}
}
