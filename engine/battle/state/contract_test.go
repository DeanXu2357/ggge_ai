package state

import (
	"errors"
	"fmt"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
)

func TestAContractStateSurvivesTheTripIntoTheStateAndBack(t *testing.T) {
	original := filledState()
	content, values, _ := FromContract(original)
	back := Battle{Content: &content, Values: &values}.ToContract()
	if !reflect.DeepEqual(back, original) {
		t.Errorf("the trip changed %s", firstDifference("state",
			reflect.ValueOf(original), reflect.ValueOf(back)))
	}
}

func TestTheExportedContractSharesNothingWithTheState(t *testing.T) {
	original := filledState()
	wantContent, wantValues, _ := FromContract(original)
	content, values, _ := FromContract(original)
	answer := Battle{Content: &content, Values: &values}.ToContract()

	*answer.Units[0].Skills[0].Amount = 404
	for index := range answer.Units[0].MapWeaponAmmo {
		answer.Units[0].MapWeaponAmmo[index] = 404
	}
	answer.Units[0].Debuffs[0].Magnitude = 404
	(*answer.Bounds)[0][0] = 404
	answer.TerrainCells[0].Terrain = battle.TerrainUnderwater

	if !reflect.DeepEqual(content, wantContent) {
		t.Errorf("a write into the answer reached the content at %s",
			firstDifference("content", reflect.ValueOf(wantContent), reflect.ValueOf(content)))
	}
	if !reflect.DeepEqual(values, wantValues) {
		t.Errorf("a write into the answer reached the values at %s",
			firstDifference("values", reflect.ValueOf(wantValues), reflect.ValueOf(values)))
	}
}

func TestACloneOfTheValuesSharesNoWritableMemoryWithItsInput(t *testing.T) {
	_, values, _ := FromContract(filledState())
	wantSkill := *values.Units[0].Skills[0].Amount
	wantAmmo, wantDebuff := values.Units[0].MapWeaponAmmo[0], values.Units[0].Debuffs[0].Magnitude

	clone := values.Clone()
	clone.Units[0].HP = 404
	*clone.Units[0].Skills[0].Amount = 404
	clone.Units[0].MapWeaponAmmo[0] = 404
	clone.Units[0].Debuffs[0].Magnitude = 404
	clone.Phase = battle.FactionThirdParty

	if values.Units[0].HP == 404 || values.Phase == battle.FactionThirdParty {
		t.Errorf("a write into the clone reached the input: %+v", values.Units[0])
	}
	if *values.Units[0].Skills[0].Amount != wantSkill ||
		values.Units[0].MapWeaponAmmo[0] != wantAmmo ||
		values.Units[0].Debuffs[0].Magnitude != wantDebuff {
		t.Errorf("a write into a slice of the clone reached the input: %+v", values.Units[0])
	}
}

func TestTheHandleOfAUnitPointsAtTheTwoColumns(t *testing.T) {
	content, values, _ := FromContract(filledState())
	view := Battle{Content: &content, Values: &values}

	unit, err := view.UnitAt(0)
	if err != nil {
		t.Fatalf("unit: %v", err)
	}
	unit.Value.HP = 404
	unit.MaxHP = 404

	if values.Units[0].HP != 404 || content.Units[0].MaxHP != 404 {
		t.Errorf("a write through the handle reached no column: %+v %+v",
			content.Units[0], values.Units[0])
	}
	if _, err := view.UnitAt(len(view.Content.Units)); !errors.Is(err, battle.ErrNoUnit) {
		t.Errorf("a position outside the columns: %v", err)
	}
}

func TestTwoUnitsWithEqualMechsPointAtTwoMechs(t *testing.T) {
	original := filledState()
	second := original.Units[0]
	second.HP = 404
	original.Units = append(original.Units, second)

	got, _, _ := FromContract(original)
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

// The lines of the contract object enter the value column as the line types
// of the engine, mech and pilot apart, and go back out in the same wire form.
func TestTheLinesOfTheContractEnterTheValueColumnAndComeBack(t *testing.T) {
	role := battle.StrikeRoleSupportDefense
	original := filledState()
	original.Units[0].Mech.Abilities = []battle.Ability{
		{Kind: battle.AbilityMechAttackPercent, Percent: 15, EnemyTag: 1015}}
	original.Units[0].Pilot.Abilities = []battle.Ability{
		{Kind: battle.AbilityMechDefensePercent, Percent: 20, MechType: battle.MechTypeDurable,
			StrikeRole: &role},
		{Kind: "squad_grant", Percent: 3}}

	content, values, err := FromContract(original)
	if err != nil {
		t.Fatal(err)
	}

	if got := values.Units[0].MechAbilities; len(got) != 1 ||
		got[0] != (lines.MechAttackPercentAgainstTag{EnemyTag: 1015, Percent: 15}) {
		t.Errorf("the mech lines: %+v", got)
	}
	if got := values.Units[0].PilotAbilities; len(got) != 2 ||
		got[0] != (lines.MechDefensePercentOnSupportDefenseWithMechType{MechType: battle.MechTypeDurable, Percent: 20}) ||
		got[1] != (lines.Unknown{Wire: original.Units[0].Pilot.Abilities[1]}) {
		t.Errorf("the pilot lines: %+v", got)
	}
	if len(values.Units[0].Hooks.OnAttack) != 1 || len(values.Units[0].Hooks.OnDefend) != 1 {
		t.Errorf("the chains: %+v", values.Units[0].Hooks)
	}
	back := Battle{Content: &content, Values: &values}.ToContract()
	if !reflect.DeepEqual(back, original) {
		t.Errorf("the trip changed %s", firstDifference("state",
			reflect.ValueOf(original), reflect.ValueOf(back)))
	}
}

// A kind the engine models, with conditions it does not, is refused: a line
// that is carried and read by nothing would be a silent zero.
func TestALineWithConditionsTheEngineDoesNotModelIsRefused(t *testing.T) {
	original := filledState()
	original.Units[0].Mech.Abilities = []battle.Ability{
		{Kind: battle.AbilityMechAttackPercent, Percent: 15, HPRateGte: 100}}

	_, _, err := FromContract(original)

	if !errors.Is(err, battle.ErrOutsideContract) {
		t.Fatalf("error: %v", err)
	}
}
