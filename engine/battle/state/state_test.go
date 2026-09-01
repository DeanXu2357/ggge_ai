package state

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func TestEveryFieldOfTheContractUnitSitsInOnePlaceOfTheState(t *testing.T) {
	contract := fieldsOf(reflect.TypeOf(battle.Unit{}))
	split := map[string]reflect.Type{}
	for name, kind := range fieldsOf(reflect.TypeOf(Unit{})) {
		if name == "Value" {
			continue
		}
		split[name] = kind
	}
	for name, kind := range fieldsOf(reflect.TypeOf(UnitValue{})) {
		if _, twice := split[name]; twice {
			t.Errorf("the field %q sits in Unit and in UnitValue", name)
			continue
		}
		split[name] = kind
	}
	for name, want := range contract {
		got, held := split[name]
		if !held {
			t.Errorf("the field %q of battle.Unit sits in no state struct", name)
			continue
		}
		if !sameShape(want, got) {
			t.Errorf("the field %q carries %s in the contract and %s in the state",
				name, want, got)
		}
	}
	for name := range split {
		if _, held := contract[name]; !held {
			t.Errorf("the field %q of the state sits in no field of battle.Unit", name)
		}
	}
}

func fieldsOf(kind reflect.Type) map[string]reflect.Type {
	out := make(map[string]reflect.Type, kind.NumField())
	for index := range kind.NumField() {
		field := kind.Field(index)
		out[field.Name] = field.Type
	}
	return out
}

func sameShape(contract, state reflect.Type) bool {
	if contract == state {
		return true
	}
	if state.Kind() == reflect.Pointer && contract.Kind() != reflect.Pointer {
		return sameShape(contract, state.Elem())
	}
	if contract.Kind() != state.Kind() {
		return false
	}
	switch contract.Kind() {
	case reflect.Array:
		return contract.Len() == state.Len() && sameShape(contract.Elem(), state.Elem())
	case reflect.Pointer, reflect.Slice:
		return sameShape(contract.Elem(), state.Elem())
	case reflect.Map:
		return contract.Key() == state.Key() && sameShape(contract.Elem(), state.Elem())
	case reflect.Struct:
		if contract.NumField() != state.NumField() {
			return false
		}
		for index := range contract.NumField() {
			if contract.Field(index).Name != state.Field(index).Name {
				return false
			}
			if !sameShape(contract.Field(index).Type, state.Field(index).Type) {
				return false
			}
		}
		return true
	default:
		return false
	}
}
