package differential_test

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
)

func init() {
	for name, op := range formulaOps {
		ops[name] = op
	}
}

type wireSide struct {
	UnitAttack   float64 `json:"unit_attack"`
	UnitDefense  float64 `json:"unit_defense"`
	PilotAttack  float64 `json:"pilot_attack"`
	PilotDefense float64 `json:"pilot_defense"`
	Reaction     float64 `json:"reaction"`
	Mobility     float64 `json:"mobility"`
}

func (side wireSide) unit() *battle.Unit {
	return &battle.Unit{
		UnitAttack:   side.UnitAttack,
		UnitDefense:  side.UnitDefense,
		PilotAttack:  side.PilotAttack,
		PilotDefense: side.PilotDefense,
		Reaction:     side.Reaction,
		Mobility:     side.Mobility,
	}
}

type strikeInput struct {
	Power    float64  `json:"power"`
	Attacker wireSide `json:"attacker"`
	Defender wireSide `json:"defender"`
}

type combatInput struct {
	Power    float64  `json:"power"`
	Attacker wireSide `json:"attacker"`
	Defender wireSide `json:"defender"`
	Terrain  float64  `json:"terrain"`
}

type scaleInput struct {
	Bonuses   float64 `json:"bonuses"`
	Penalties float64 `json:"penalties"`
}

type finalInput struct {
	CombatBase        float64 `json:"combat_base"`
	Scale             float64 `json:"scale"`
	DefenseMultiplier float64 `json:"defense_multiplier"`
}

type criticalInput struct {
	CombatBase        float64 `json:"combat_base"`
	Scale             float64 `json:"scale"`
	DefenseMultiplier float64 `json:"defense_multiplier"`
	Critical          float64 `json:"critical"`
}

type expectedInput struct {
	Power             float64  `json:"power"`
	Attacker          wireSide `json:"attacker"`
	Defender          wireSide `json:"defender"`
	Terrain           float64  `json:"terrain"`
	Bonuses           float64  `json:"bonuses"`
	Penalties         float64  `json:"penalties"`
	DefenseMultiplier float64  `json:"defense_multiplier"`
}

type hitInput struct {
	Attacker          wireSide `json:"attacker"`
	Defender          wireSide `json:"defender"`
	AbilityCorrection float64  `json:"ability_correction"`
}

func decodeInput(input json.RawMessage, into any) error {
	decoder := json.NewDecoder(bytes.NewReader(input))
	decoder.DisallowUnknownFields()
	return decoder.Decode(into)
}

var formulaOps = map[string]differential.Op{
	"base_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in strikeInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.BaseDamage(in.Power, in.Attacker.unit(), in.Defender.unit()), nil
	},
	"combat_base_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in combatInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.CombatBaseDamage(in.Power, in.Attacker.unit(), in.Defender.unit(),
			in.Terrain), nil
	},
	"damage_scale": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in scaleInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.DamageScale(in.Bonuses, in.Penalties), nil
	},
	"final_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in finalInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.FinalDamage(in.CombatBase, in.Scale, in.DefenseMultiplier), nil
	},
	"critical_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in criticalInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.CriticalDamage(in.CombatBase, in.Scale, in.DefenseMultiplier,
			in.Critical), nil
	},
	"expected_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in expectedInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		combatBase := battle.CombatBaseDamage(in.Power, in.Attacker.unit(), in.Defender.unit(),
			in.Terrain)
		scale := battle.DamageScale(in.Bonuses, in.Penalties)
		return battle.FinalDamage(combatBase, scale, in.DefenseMultiplier), nil
	},
	"hit_rate_percent": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in hitInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.HitRatePercent(in.Attacker.unit(), in.Defender.unit(),
			in.AbilityCorrection), nil
	},
	"hit_probability": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in hitInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return battle.HitProbability(in.Attacker.unit(), in.Defender.unit(),
			in.AbilityCorrection), nil
	},
}

func TestTheFormulaCaseRunsEveryPortedFormula(t *testing.T) {
	var formulas *differential.Case
	for _, one := range load(t) {
		if one.Name == "formulas" {
			formulas = one
		}
	}
	if formulas == nil {
		t.Fatal("the case file formulas.json is missing")
	}

	result := differential.Run(formulas, ops)

	for _, err := range result.Errs {
		t.Error(err)
	}
	if len(result.Skipped) != 0 {
		t.Fatalf("skipped ops: %v", result.Skipped)
	}
	ran := map[string]int{}
	for _, name := range result.Ran {
		ran[name]++
	}
	for name := range formulaOps {
		if ran[name] == 0 {
			t.Errorf("the case holds no check of %q", name)
		}
	}
}

func TestAFormulaInputOutsideTheContractStopsTheOp(t *testing.T) {
	op := ops["damage_scale"]

	if _, err := op(nil, json.RawMessage(`{"bonuses":0.1,"morale":7}`)); err == nil {
		t.Fatal("a field that the op does not hold must stop the check")
	}
}
