package differential_test

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
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

func (side wireSide) unit() *battle.Unit {
	return &battle.Unit{
		Pilot: battle.Pilot{
			Ranged:   side.PilotAttack,
			Melee:    side.PilotAttack,
			Awaken:   side.PilotAttack,
			Defense:  side.PilotDefense,
			Reaction: side.Reaction,
		},
		Mech: battle.Mech{
			Attack:   side.UnitAttack,
			Defense:  side.UnitDefense,
			Mobility: side.Mobility,
		},
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

func (in hitInput) weapon() battle.Weapon {
	return battle.Weapon{Accuracy: in.Accuracy}
}

// The recorded inputs name the power alone. The three pilot values of a side
// hold the one recorded number, so an untagged weapon reads it back.
func shot(power float64) battle.Weapon {
	return battle.Weapon{Power: power}
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
		return board.BaseDamage(shot(in.Power), in.Attacker.unit(), in.Defender.unit()), nil
	},
	"combat_base_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in combatInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.CombatBaseDamage(shot(in.Power), in.Attacker.unit(), in.Defender.unit(),
			in.Terrain), nil
	},
	"damage_scale": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in scaleInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.DamageScale(in.Bonuses, in.Penalties), nil
	},
	"final_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in finalInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.FinalDamage(in.CombatBase, in.Scale, in.DefenseMultiplier), nil
	},
	"critical_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in criticalInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.CriticalDamage(in.CombatBase, in.Scale, in.DefenseMultiplier,
			in.Critical), nil
	},
	"expected_damage": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in expectedInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.ExpectedDamage(shot(in.Power), in.Attacker.unit(), in.Defender.unit(),
			in.Terrain, in.Bonuses, in.Penalties, in.DefenseMultiplier), nil
	},
	"hit_rate_percent": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in hitInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.HitRatePercent(in.weapon(), in.Attacker.unit(), in.Defender.unit(),
			in.AbilityCorrection), nil
	},
	"hit_probability": func(_ *differential.Setup, input json.RawMessage) (any, error) {
		var in hitInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		return board.HitProbability(in.weapon(), in.Attacker.unit(), in.Defender.unit(),
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
