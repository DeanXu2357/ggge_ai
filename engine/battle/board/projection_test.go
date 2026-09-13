package board

import (
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/system"
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
		"no bounds": {Phase: ally, Units: []battle.Unit{{Faction: ally}}},
		"no phase": {
			Bounds: &square,
			Units:  []battle.Unit{{Faction: ally}},
		},
		"an unknown faction": {
			Bounds: &square,
			Phase:  ally,
			Units:  []battle.Unit{{Faction: battle.Faction("pirate")}},
		},
		"an ammunition count for a map weapon the unit does not carry": {
			Bounds: &square,
			Phase:  ally,
			Units:  []battle.Unit{{Faction: ally, MapWeaponAmmo: []int{3}}},
		},
		"a size below zero": {
			Bounds: &square,
			Phase:  ally,
			Units: []battle.Unit{{
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

	encoded := skillEntriesOf([]def.Skill{{Kind: "skill_heal", Amount: &amount}})
	amount = 0

	if *encoded[0].Amount != 2500.0 {
		t.Fatalf("skill: %+v", encoded[0])
	}
}

func TestTheEngagementPayloadCarriesTheOptionsOfTheTwoSides(t *testing.T) {
	counter := system.Forecast{}
	encoded := responseAttacksOf(system.Options{
		Defender: system.SideOptions{UnitID: 0,
			SupportDefenders: []system.SupportDefendOption{{UnitID: 2}},
			SupportAttackers: []system.SupportAttackOption{{UnitID: 2, WeaponID: 1}}},
		Attacker: system.SideOptions{UnitID: 1},
		ResponseAttacks: []system.ResponseAttackOption{
			{Stance: battle.StanceDodge},
			{Stance: battle.StanceCounter, WeaponID: idOf(3), Counter: &counter},
			{Stance: battle.StanceNone},
		},
	})

	if encoded.Defender.UnitID != 0 || encoded.Attacker.UnitID != 1 {
		t.Fatalf("sides: %+v", encoded)
	}
	if encoded.Defender.ResponseAttacks[0].Stance != battle.StanceDodge ||
		encoded.Defender.ResponseAttacks[0].WeaponID != nil ||
		encoded.Defender.ResponseAttacks[0].Counter != nil {
		t.Fatalf("dodge: %+v", encoded.Defender.ResponseAttacks[0])
	}
	if *encoded.Defender.ResponseAttacks[1].WeaponID != 3 ||
		encoded.Defender.ResponseAttacks[1].Counter == nil {
		t.Fatalf("a counter carries the forecast of its own strike: %+v",
			encoded.Defender.ResponseAttacks[1])
	}
	if encoded.Defender.ResponseAttacks[2].Stance != battle.StanceNone {
		t.Fatalf("the stand: %+v", encoded.Defender.ResponseAttacks[2])
	}
	if encoded.Defender.SupportDefenders[0].UnitID != 2 ||
		encoded.Defender.SupportAttackers[0].WeaponID != 1 {
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

	full := forecastOf(system.Forecast{HitRate: &rate, Damage: &damage, Kill: &kill})
	lean := forecastOf(system.Forecast{Damage: &damage})

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
