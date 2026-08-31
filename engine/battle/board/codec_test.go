package board

import (
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
)

func TestAWeaponCategoryOutsideTheContractStopsTheDecode(t *testing.T) {
	var weapon battle.Weapon

	err := json.Unmarshal([]byte(`{"name":"rifle","categories":["psychic"]}`), &weapon)

	if err == nil {
		t.Fatal("a category outside the contract must stop the decode")
	}
}

func TestDecodeRefusesAPayloadOutsideTheContract(t *testing.T) {
	square := battle.Bounds{{0, 0}, {4, 4}}
	ally := battle.FactionAlly
	cases := map[string]*battle.BattleState{
		"no state":  nil,
		"no bounds": {Phase: ally, Units: []battle.Unit{{ID: "a1", Faction: ally}}},
		"no phase": {
			Bounds: &square,
			Units:  []battle.Unit{{ID: "a1", Faction: ally}},
		},
		"an unknown faction": {
			Bounds: &square,
			Phase:  ally,
			Units:  []battle.Unit{{ID: "a1", Faction: battle.Faction("pirate")}},
		},
		"two units with one id": {
			Bounds: &square,
			Phase:  ally,
			Units: []battle.Unit{
				{ID: "a1", Faction: ally},
				{ID: "a1", Faction: battle.FactionEnemy},
			},
		},
		"a size below zero": {
			Bounds: &square,
			Phase:  ally,
			Units: []battle.Unit{{
				ID:      "a1",
				Faction: ally,
				Size:    battle.Cell{-1, 2},
			}},
		},
		"bounds that run backward": {
			Bounds: &battle.Bounds{{4, 4}, {0, 0}},
			Phase:  ally,
		},
	}

	for name, wire := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := restore(wire); err == nil {
				t.Fatal("the decode took a payload outside the contract")
			}
		})
	}
}

func TestTheEncodedSkillSharesNoMemoryWithTheModel(t *testing.T) {
	amount := 2500.0

	encoded := encodeSkills([]battle.Skill{{Kind: "skill_heal", Amount: &amount}})
	amount = 0

	if *encoded[0].Amount != 2500.0 {
		t.Fatalf("skill: %+v", encoded[0])
	}
}

func TestTheEngagementPayloadCarriesTheOptionsOfTheTwoSides(t *testing.T) {
	defender := &battle.Unit{ID: "d1", HP: 100}
	attacker := &battle.Unit{ID: "e1", HP: 100}
	helper := &battle.Unit{ID: "h1", HP: 100, Mech: battle.Mech{Weapons: []battle.Weapon{{Name: "rifle"}}}}

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
	if encoded.Defender.ResponseAttacks[0].Stance != battle.StanceDodge ||
		encoded.Defender.ResponseAttacks[0].Weapon != nil ||
		encoded.Defender.ResponseAttacks[0].Counter != nil {
		t.Fatalf("dodge: %+v", encoded.Defender.ResponseAttacks[0])
	}
	if *encoded.Defender.ResponseAttacks[1].Weapon != "saber" ||
		encoded.Defender.ResponseAttacks[1].Counter == nil {
		t.Fatalf("a counter carries the forecast of its own strike: %+v",
			encoded.Defender.ResponseAttacks[1])
	}
	if encoded.Defender.ResponseAttacks[2].Stance != battle.StanceNone {
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
	moveTo := battle.Cell{4, 5}
	name := "rifle"
	target := "e1"

	action, err := decodeDecision(&battle.Decision{
		UnitID: "a1", Kind: battle.ActionAttack, MoveTo: &moveTo,
		TargetID: &target, Weapon: &name,
	})

	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if action.Kind != engagement.ActionAttack || *action.MoveTo != (battle.Cell{4, 5}) ||
		action.Weapon != "rifle" || action.TargetID != "e1" {
		t.Fatalf("action: %+v", action)
	}
	lean, err := decodeDecision(&battle.Decision{UnitID: "a1", Kind: battle.ActionStandby})
	if err != nil || lean.MoveTo != nil || lean.Weapon != "" {
		t.Fatalf("a field with no value stays empty: %+v, %v", lean, err)
	}
}
