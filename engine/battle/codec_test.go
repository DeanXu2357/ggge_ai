package battle

import (
	"reflect"
	"testing"

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
					Kind:            protocol.ActionSkillHeal,
					Source:          protocol.SourceUnit,
					Amount:          &amount,
					Uses:            2,
					EndsActivation:  true,
					UsableAfterMove: true,
					RangeMax:        1,
					Blast:           1,
					Affects:         protocol.AffectsAlly,
				}},
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
					CanCounter:      true,
					MapWeapon:       false,
					UsableAfterMove: true,
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

	amount := 3000.0
	want := Unit{
		ID:                      "a1",
		Faction:                 FactionAlly,
		Footprint:               Footprint{Anchor: Cell{2, 3}, Size: Size{2, 3}},
		HP:                      8200,
		MaxHP:                   9000,
		EN:                      120,
		ENMax:                   180,
		Pilot:                   Pilot{Attack: 220, Defense: 190, Reaction: 205},
		Mech:                    Mech{Attack: 4100, Defense: 3900, Mobility: 310},
		MoveRange:               4,
		Acted:                   true,
		SupportDefendCharges:    1,
		SupportDefendChargesMax: 1,
		SupportAttackCharges:    2,
		HasShield:               true,
		AttackShield:            true,
		Ammo:                    map[string]int{"missile": 3},
		Weapons: []Weapon{{
			Name:            "rifle",
			Power:           2400,
			Range:           RadiusRange{Min: 1, Max: 4},
			ENCost:          15,
			Accuracy:        12,
			CanCounter:      true,
			UsableAfterMove: true,
			Blast:           1,
			DebuffKind:      "mobility",
			DebuffMagnitude: 0.2,
		}},
		Skills: []Skill{{
			Kind:            ActionSkillHeal,
			Source:          SourceUnit,
			Amount:          &amount,
			Uses:            2,
			EndsActivation:  true,
			UsableAfterMove: true,
			Range:           RadiusRange{Min: 0, Max: 1},
			Blast:           1,
			Affects:         AffectsAlly,
		}},
		Debuffs: []Debuff{{Kind: "mobility", Magnitude: 0.2, AppliedPhase: 1}},
	}
	if got := board.Unit("a1"); !reflect.DeepEqual(*got, want) {
		t.Fatalf("unit:\n%+v\n%+v", *got, want)
	}
	if got := board.Bounds; got != (Bounds{Low: Cell{0, 0}, High: Cell{9, 9}}) {
		t.Fatalf("bounds: %+v", got)
	}
	if board.Phase != FactionAlly || board.Turn != 3 {
		t.Fatalf("phase %q, turn %d", board.Phase, board.Turn)
	}
}

func TestTheModelCopiesTheAmmoAndTheSkillAmount(t *testing.T) {
	state := wireBoard()

	board, err := DecodeState(state)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	unit := board.Unit("a1")
	unit.Ammo["missile"] = 0
	*unit.Skills[0].Amount = 1.0

	if state.Units[0].Ammo["missile"] != 3 || *state.Units[0].Skills[0].Amount != 3000.0 {
		t.Fatal("a write into the model reached the payload")
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
		Phase:  protocol.FactionAlly,
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
		"a skill kind outside the contract": {
			Bounds: &square,
			Phase:  ally,
			Units: []protocol.Unit{{
				UnitID:  "a1",
				Faction: ally,
				Skills:  []protocol.Skill{{Kind: protocol.ActionKind("pray")}},
			}},
		},
		"a skill source outside the contract": {
			Bounds: &square,
			Phase:  ally,
			Units: []protocol.Unit{{
				UnitID:  "a1",
				Faction: ally,
				Skills: []protocol.Skill{{
					Kind:    protocol.ActionSkillHeal,
					Source:  protocol.SkillSource("squad"),
					Affects: protocol.AffectsAlly,
				}},
			}},
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

func TestAnEnumeratedActionSettlesNoDie(t *testing.T) {
	amount := 2500.0
	cell := Cell{4, 5}

	full := EncodeDecision(Decision{
		UnitID:   "a1",
		Kind:     ActionAttack,
		MoveTo:   &cell,
		TargetID: "e1",
		Weapon:   "rifle",
		Amount:   &amount,
		Aim:      &cell,
		Support:  true,
	})
	lean := EncodeDecision(Decision{UnitID: "a1", Kind: ActionStandby})

	if full.Kind != protocol.ActionAttack || *full.TargetID != "e1" || *full.Weapon != "rifle" {
		t.Fatalf("decision: %+v", full)
	}
	if *full.MoveTo != (protocol.Cell{4, 5}) || *full.Aim != (protocol.Cell{4, 5}) {
		t.Fatalf("cells: %+v", full)
	}
	if *full.Amount != amount || !full.Support {
		t.Fatalf("amount and support: %+v", full)
	}
	if full.Hit != nil || full.CounterHit != nil || full.SupportHit != nil || full.Reaction != nil {
		t.Fatalf("an enumerated action carries no die and no reaction: %+v", full)
	}
	if lean.MoveTo != nil || lean.TargetID != nil || lean.Weapon != nil || lean.Amount != nil ||
		lean.Aim != nil || lean.Support {
		t.Fatalf("a field with no value is null: %+v", lean)
	}
}

func TestTheEncodedDecisionSharesNoMemoryWithTheModel(t *testing.T) {
	amount := 2500.0
	cell := Cell{4, 5}

	encoded := EncodeDecision(Decision{UnitID: "a1", Kind: ActionSkillHeal, Amount: &amount, Aim: &cell})
	amount = 0
	cell = Cell{0, 0}

	if *encoded.Amount != 2500.0 || *encoded.Aim != (protocol.Cell{4, 5}) {
		t.Fatalf("decision: %+v", encoded)
	}
}

func TestTheReactionListEncodesEveryFieldAndKeepsItsOrder(t *testing.T) {
	encoded := EncodeReactions([]Reaction{
		{Stance: StanceDodge, SupportAttack: true},
		{Stance: StanceCounter, Weapon: "saber", SupportDefend: true},
	})

	if len(encoded) != 2 {
		t.Fatalf("reactions: %+v", encoded)
	}
	if encoded[0].Stance != protocol.StanceDodge || encoded[0].Weapon != nil ||
		encoded[0].SupportDefend || !encoded[0].SupportAttack {
		t.Fatalf("dodge: %+v", encoded[0])
	}
	if encoded[1].Stance != protocol.StanceCounter || *encoded[1].Weapon != "saber" ||
		!encoded[1].SupportDefend || encoded[1].SupportAttack {
		t.Fatalf("counter: %+v", encoded[1])
	}
}

func TestAnEmptyReactionListEncodesToAnEmptyList(t *testing.T) {
	if got := EncodeReactions(nil); got == nil || len(got) != 0 {
		t.Fatalf("reactions: %v", got)
	}
	if got := EncodeDecisions(nil); got == nil || len(got) != 0 {
		t.Fatalf("decisions: %v", got)
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

func TestTheRulesOfAStageOverrideTheDefaults(t *testing.T) {
	payload := protocol.Rules{
		DefendMultiplier:        0.7,
		ShieldMultiplier:        0.5,
		SupportDefendMultiplier: 0.75,
		DodgeHitPenalty:         25,
		Terrain:                 1.2,
		MaxSupportAttackers:     2,
		ENRegenFraction:         0.15,
	}

	rules, err := DecodeRules(&payload)
	if err != nil {
		t.Fatalf("rules: %v", err)
	}

	want := Rules{
		DefendMultiplier:        0.7,
		ShieldMultiplier:        0.5,
		SupportDefendMultiplier: 0.75,
		DodgeHitPenalty:         25,
		Terrain:                 1.2,
		MaxSupportAttackers:     2,
		ENRegenFraction:         0.15,
	}
	if rules != want {
		t.Fatalf("rules: %+v", rules)
	}
}

func TestAPayloadWithNoRulesTakesTheDefaults(t *testing.T) {
	rules, err := DecodeRules(nil)
	if err != nil {
		t.Fatalf("rules: %v", err)
	}

	if rules != DefaultRules() {
		t.Fatalf("rules: %+v", rules)
	}
	if rules.Terrain != 1 || rules.MaxSupportAttackers != 3 || rules.DodgeHitPenalty != 20 {
		t.Fatalf("the defaults of docs/reference/combat-formulas.md: %+v", rules)
	}
}

// A payload that carries the rules carries every field. A partial payload
// decodes the fields it omits to zero, and each check below names one such
// field.
func TestAPartialRulePayloadIsNoRuleSet(t *testing.T) {
	full := protocol.Rules{
		DefendMultiplier:        0.7,
		ShieldMultiplier:        0.5,
		SupportDefendMultiplier: 0.75,
		DodgeHitPenalty:         25,
		Terrain:                 1.2,
		MaxSupportAttackers:     2,
		ENRegenFraction:         0.15,
	}
	cases := map[string]func(*protocol.Rules){
		"no defend multiplier": func(one *protocol.Rules) { one.DefendMultiplier = 0 },
		"no shield multiplier": func(one *protocol.Rules) { one.ShieldMultiplier = 0 },
		"no support defense multiplier": func(one *protocol.Rules) {
			one.SupportDefendMultiplier = 0
		},
		"a multiplier above one":     func(one *protocol.Rules) { one.DefendMultiplier = 1.5 },
		"a dodge penalty below zero": func(one *protocol.Rules) { one.DodgeHitPenalty = -1 },
		"no terrain":                 func(one *protocol.Rules) { one.Terrain = 0 },
		"a terrain below zero":       func(one *protocol.Rules) { one.Terrain = -1 },
		"a support cap below zero":   func(one *protocol.Rules) { one.MaxSupportAttackers = -1 },
		"a regeneration below zero":  func(one *protocol.Rules) { one.ENRegenFraction = -0.1 },
		"a regeneration above one":   func(one *protocol.Rules) { one.ENRegenFraction = 1.5 },
	}

	for name, spoil := range cases {
		t.Run(name, func(t *testing.T) {
			payload := full
			spoil(&payload)

			if _, err := DecodeRules(&payload); err == nil {
				t.Fatalf("the rules stand outside the mechanism: %+v", payload)
			}
		})
	}
	if _, err := DecodeRules(&full); err != nil {
		t.Fatalf("rules: %v", err)
	}
}

func TestABoardStartsWithTheDefaultRules(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	if board.Rules != DefaultRules() {
		t.Fatalf("rules: %+v", board.Rules)
	}
}

func TestTheDecodedDecisionCarriesItsReactionAndNoDie(t *testing.T) {
	cell := protocol.Cell{4, 5}
	amount := 2500.0
	weapon := "saber"
	target := "e1"
	landed := true

	decision, err := DecodeDecision(protocol.Decision{
		UnitID:     "a1",
		Kind:       protocol.ActionAttack,
		MoveTo:     &cell,
		TargetID:   &target,
		Weapon:     &weapon,
		Amount:     &amount,
		Aim:        &cell,
		Support:    true,
		Hit:        &landed,
		CounterHit: &landed,
		SupportHit: &landed,
		Reaction: &protocol.Reaction{
			Stance:        protocol.StanceCounter,
			Weapon:        &weapon,
			SupportDefend: true,
		},
	})
	if err != nil {
		t.Fatalf("decision: %v", err)
	}

	if decision.Kind != ActionAttack || decision.TargetID != "e1" || decision.Weapon != "saber" {
		t.Fatalf("decision: %+v", decision)
	}
	if decision.MoveTo == nil || *decision.MoveTo != (Cell{4, 5}) || *decision.Amount != amount {
		t.Fatalf("decision: %+v", decision)
	}
	if decision.Reaction == nil || decision.Reaction.Stance != StanceCounter ||
		decision.Reaction.Weapon != "saber" || !decision.Reaction.SupportDefend ||
		decision.Reaction.SupportAttack {
		t.Fatalf("reaction: %+v", decision.Reaction)
	}
	if again := EncodeDecision(decision); again.Reaction == nil ||
		again.Reaction.Stance != protocol.StanceCounter {
		t.Fatalf("the encoder writes the reaction back: %+v", again)
	}
}

func TestADecisionOutsideTheContractStopsTheDecode(t *testing.T) {
	if _, err := DecodeDecision(protocol.Decision{Kind: protocol.ActionKind("pray")}); err == nil {
		t.Fatal("the kind is not in the contract")
	}
	_, err := DecodeDecision(protocol.Decision{
		Kind:     protocol.ActionAttack,
		Reaction: &protocol.Reaction{Stance: protocol.Stance("none")},
	})
	if err == nil {
		t.Fatal("the stance is not in the contract")
	}
}

func TestTheEncodedUnitCarriesEveryFieldAndNoNullList(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	encoded := EncodeUnit(*board.Unit("a1"))
	lean := EncodeUnit(*board.Unit("e1"))

	if !reflect.DeepEqual(encoded, wireBoard().Units[0]) {
		t.Fatalf("unit:\n%+v\n%+v", encoded, wireBoard().Units[0])
	}
	if lean.Weapons == nil || lean.Skills == nil || lean.Debuffs == nil || lean.Ammo == nil {
		t.Fatalf("an empty list is no null: %+v", lean)
	}
	if got := EncodeUnits(board.Units); len(got) != 2 || got[1].UnitID != "e1" {
		t.Fatalf("units: %+v", got)
	}
}

func TestThePhaseIndexCountsTheThreeSidesOfEveryTurn(t *testing.T) {
	board, err := DecodeState(wireBoard())
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	first := board.PhaseIndex()
	board.Phase = FactionEnemy
	last := board.PhaseIndex()

	if PhaseOrder != [...]Faction{FactionAlly, FactionThirdParty, FactionEnemy} {
		t.Fatalf("order: %v", PhaseOrder)
	}
	if first != 9 || last != 11 {
		t.Fatalf("turn 3 holds the phases 9 to 11: %d %d", first, last)
	}
}
