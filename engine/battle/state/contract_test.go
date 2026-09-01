package state

import (
	"fmt"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func TestAContractStateSurvivesTheTripIntoTheStateAndBack(t *testing.T) {
	original := filledState()
	inside := FromContract(original)
	back := inside.ToContract()
	if !reflect.DeepEqual(back, original) {
		t.Errorf("the trip changed %s", firstDifference("state",
			reflect.ValueOf(original), reflect.ValueOf(back)))
	}
}

func TestTheExportedContractSharesNothingWithTheState(t *testing.T) {
	original := filledState()
	want := FromContract(original)
	got := FromContract(original)
	answer := got.ToContract()

	*answer.Units[0].Skills[0].Amount = 404
	for name := range answer.Units[0].Ammo {
		answer.Units[0].Ammo[name] = 404
	}
	answer.Units[0].Debuffs[0].Magnitude = 404
	(*answer.Bounds)[0][0] = 404
	answer.TerrainCells[0].Terrain = battle.TerrainUnderwater

	if !reflect.DeepEqual(got, want) {
		t.Errorf("a write into the answer reached the state at %s",
			firstDifference("state", reflect.ValueOf(want), reflect.ValueOf(got)))
	}
}

func TestTwoUnitsWithEqualMechsPointAtTwoMechs(t *testing.T) {
	original := filledState()
	second := original.Units[0]
	second.ID = "second"
	original.Units = append(original.Units, second)

	got := FromContract(original)
	if got.Units[0].Mech == got.Units[1].Mech {
		t.Fatal("the two units point at one mech")
	}
	got.Units[0].Mech.MoveRange = 404
	if got.Units[1].Mech.MoveRange == 404 {
		t.Error("a write into the mech of the first unit reached the second unit")
	}
}

func filledState() battle.BattleState {
	var out battle.BattleState
	f := &filler{}
	f.fill(reflect.ValueOf(&out).Elem())
	out.PendingEvents = nil
	out.FiredEvents = nil
	out.Bounds = &battle.Bounds{{0, 0}, {19, 19}}
	out.Units[0].Pos = battle.Cell{2, 3}
	out.Units[0].Size = battle.Cell{1, 2}
	return out
}

type filler struct {
	count int
}

func (f *filler) next() int {
	f.count++
	return f.count
}

func (f *filler) fill(v reflect.Value) {
	switch v.Type() {
	case reflect.TypeFor[battle.Faction]():
		v.SetString(string(battle.FactionEnemy))
		return
	case reflect.TypeFor[battle.SkillSource]():
		v.SetString(string(battle.SourceCrew))
		return
	case reflect.TypeFor[battle.SkillAffects]():
		v.SetString(string(battle.AffectsEnemy))
		return
	case reflect.TypeFor[battle.Direction]():
		v.SetString(string(battle.DirectionLeft))
		return
	case reflect.TypeFor[battle.MapWeaponAffects]():
		v.SetString(string(battle.MapWeaponAffectsAll))
		return
	case reflect.TypeFor[battle.WeaponCategory]():
		v.SetString(string(battle.WeaponCategoryMelee))
		return
	case reflect.TypeFor[battle.Terrain]():
		v.SetString(string(battle.TerrainGround))
		return
	}
	switch v.Kind() {
	case reflect.Bool:
		v.SetBool(true)
	case reflect.Int:
		v.SetInt(int64(f.next()))
	case reflect.Float64:
		v.SetFloat(float64(f.next()) + 0.5)
	case reflect.String:
		v.SetString(fmt.Sprintf("name-%d", f.next()))
	case reflect.Pointer:
		item := reflect.New(v.Type().Elem())
		f.fill(item.Elem())
		v.Set(item)
	case reflect.Slice:
		items := reflect.MakeSlice(v.Type(), 1, 1)
		f.fill(items.Index(0))
		v.Set(items)
	case reflect.Array:
		for index := range v.Len() {
			f.fill(v.Index(index))
		}
	case reflect.Map:
		items := reflect.MakeMap(v.Type())
		key := reflect.New(v.Type().Key()).Elem()
		f.fill(key)
		item := reflect.New(v.Type().Elem()).Elem()
		f.fill(item)
		items.SetMapIndex(key, item)
		v.Set(items)
	case reflect.Struct:
		for index := range v.NumField() {
			f.fill(v.Field(index))
		}
	default:
		panic(fmt.Sprintf("the filler holds no value for %s", v.Type()))
	}
}

func firstDifference(path string, want, got reflect.Value) string {
	if want.Type() != got.Type() {
		return fmt.Sprintf("%s: the type %s against the type %s",
			path, want.Type(), got.Type())
	}
	switch want.Kind() {
	case reflect.Pointer:
		if want.IsNil() != got.IsNil() {
			return fmt.Sprintf("%s: one side is nil", path)
		}
		if want.IsNil() {
			return ""
		}
		return firstDifference(path, want.Elem(), got.Elem())
	case reflect.Slice:
		if want.IsNil() != got.IsNil() {
			return fmt.Sprintf("%s: one side is nil", path)
		}
		if want.Len() != got.Len() {
			return fmt.Sprintf("%s: %d items against %d items",
				path, want.Len(), got.Len())
		}
		fallthrough
	case reflect.Array:
		for index := range want.Len() {
			step := fmt.Sprintf("%s[%d]", path, index)
			if out := firstDifference(step, want.Index(index), got.Index(index)); out != "" {
				return out
			}
		}
		return ""
	case reflect.Struct:
		for index := range want.NumField() {
			step := path + "." + want.Type().Field(index).Name
			if out := firstDifference(step, want.Field(index), got.Field(index)); out != "" {
				return out
			}
		}
		return ""
	default:
		if reflect.DeepEqual(want.Interface(), got.Interface()) {
			return ""
		}
		return fmt.Sprintf("%s: %v against %v", path, want.Interface(), got.Interface())
	}
}
