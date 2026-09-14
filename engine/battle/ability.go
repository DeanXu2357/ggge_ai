package battle

import (
	"encoding/json"
	"fmt"
	"reflect"
	"slices"
)

// AbilityKind names one effect line of the mech or of the pilot. The set is
// the engine's own division of the trait rows of the game, and a kind enters
// the set when a scenario needs it.
type AbilityKind string

const (
	AbilityMechAttackPercent  AbilityKind = "mech_attack_percent"
	AbilityMechDefensePercent AbilityKind = "mech_defense_percent"
)

// Ability is one line on the wire. Each kind is its own struct with the
// fields that kind reads, effect and condition alike; the value of 'kind'
// picks the struct when a line is decoded.
type Ability interface {
	Kind() AbilityKind
}

type MechAttackPercent struct {
	EnemyTags []int   `json:"enemy_tags"`
	Percent   float64 `json:"percent"`
}

func (MechAttackPercent) Kind() AbilityKind { return AbilityMechAttackPercent }

type MechDefensePercent struct {
	EnemyTags []int   `json:"enemy_tags"`
	Percent   float64 `json:"percent"`
}

func (MechDefensePercent) Kind() AbilityKind { return AbilityMechDefensePercent }

type Abilities []Ability

var abilityKinds = map[AbilityKind]func() Ability{
	AbilityMechAttackPercent:  func() Ability { return MechAttackPercent{} },
	AbilityMechDefensePercent: func() Ability { return MechDefensePercent{} },
}

// UnknownAbility holds a line of a kind that the engine does not model. No
// hook reads it, and the encoder writes it back as it came (issue #80).
type UnknownAbility struct {
	K   AbilityKind
	Raw json.RawMessage
}

func (u UnknownAbility) Kind() AbilityKind { return u.K }

func (u UnknownAbility) MarshalJSON() ([]byte, error) { return u.Raw, nil }

func (a Abilities) MarshalJSON() ([]byte, error) {
	// A nil list writes 'null' and an empty list writes '[]', because that is
	// what 'encoding/json' gives every other list of the contract.
	if a == nil {
		return []byte("null"), nil
	}
	out := make([]json.RawMessage, len(a))
	for index, line := range a {
		item, err := encodeAbility(line)
		if err != nil {
			return nil, err
		}
		out[index] = item
	}
	return json.Marshal(out)
}

func (a *Abilities) UnmarshalJSON(data []byte) error {
	var raw []json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("abilities: %w", err)
	}
	if raw == nil {
		*a = nil
		return nil
	}
	out := make(Abilities, len(raw))
	for index, item := range raw {
		line, err := decodeAbility(item)
		if err != nil {
			return err
		}
		out[index] = line
	}
	*a = out
	return nil
}

func encodeAbility(line Ability) ([]byte, error) {
	if unknown, carried := line.(UnknownAbility); carried {
		return unknown.MarshalJSON()
	}
	body, err := json.Marshal(line)
	if err != nil {
		return nil, err
	}
	if len(body) < 2 || body[0] != '{' {
		return nil, fmt.Errorf("the ability %q writes no object", line.Kind())
	}
	kind, err := json.Marshal(line.Kind())
	if err != nil {
		return nil, err
	}
	head := append([]byte(`{"kind":`), kind...)
	if len(body) == 2 {
		return append(head, '}'), nil
	}
	return append(append(head, ','), body[1:]...), nil
}

func decodeAbility(raw json.RawMessage) (Ability, error) {
	var head struct {
		Kind AbilityKind `json:"kind"`
	}
	if err := json.Unmarshal(raw, &head); err != nil {
		return nil, fmt.Errorf("ability: %w", err)
	}
	zero, known := abilityKinds[head.Kind]
	if !known {
		return UnknownAbility{K: head.Kind, Raw: slices.Clone(raw)}, nil
	}
	line := reflect.New(reflect.TypeOf(zero()))
	if err := json.Unmarshal(raw, line.Interface()); err != nil {
		return nil, fmt.Errorf("the ability %q: %w", head.Kind, err)
	}
	return line.Elem().Interface().(Ability), nil
}
