package differential_test

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle/formula"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
)

func init() {
	addOps(formulaOps)
}

type wireSide struct {
	UnitAttack   float64 `json:"unit_attack"`
	UnitDefense  float64 `json:"unit_defense"`
	PilotAttack  float64 `json:"pilot_attack"`
	PilotDefense float64 `json:"pilot_defense"`
	Reaction     float64 `json:"reaction"`
	Mobility     float64 `json:"mobility"`
}

func (in wireSide) side() formula.Side {
	return formula.Side{
		PilotAttack:   in.PilotAttack,
		PilotDefense:  in.PilotDefense,
		PilotReaction: in.Reaction,
		MechAttack:    in.UnitAttack,
		MechDefense:   in.UnitDefense,
		Mobility:      in.Mobility,
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
	Accuracy          float64  `json:"accuracy"`
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
		return formula.BaseDamage(in.Power, in.Attacker.side(), in.Defender.side()), nil
	},
	"combat_base_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in combatInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.CombatBaseDamage(in.Power, in.Attacker.side(), in.Defender.side(),
			in.Terrain), nil
	},
	"damage_scale": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in scaleInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.DamageScale(in.Bonuses, in.Penalties), nil
	},
	"final_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in finalInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.FinalDamage(in.CombatBase, in.Scale, in.DefenseMultiplier), nil
	},
	"critical_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in criticalInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.CriticalDamage(in.CombatBase, in.Scale, in.DefenseMultiplier,
			in.Critical), nil
	},
	"expected_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in expectedInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.ExpectedDamage(in.Power, in.Attacker.side(), in.Defender.side(),
			in.Terrain, in.Bonuses, in.Penalties, in.DefenseMultiplier), nil
	},
	"hit_rate_percent": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in hitInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.HitRatePercent(in.Accuracy, in.Attacker.side(), in.Defender.side(),
			in.AbilityCorrection), nil
	},
	"hit_probability": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in hitInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return formula.HitProbability(in.Accuracy, in.Attacker.side(), in.Defender.side(),
			in.AbilityCorrection), nil
	},
}

func TestTheFormulaCaseHoldsACheckOfEveryPortedFormula(t *testing.T) {
	formulas, err := differential.Load(filepath.Join(fixtures, "formulas.json"))
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	written := map[string]int{}
	for _, check := range formulas.Checks {
		written[check.Op]++
	}
	for name := range formulaOps {
		if written[name] == 0 {
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
