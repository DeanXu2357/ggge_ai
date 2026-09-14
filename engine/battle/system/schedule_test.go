package system

import (
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func scheduled(t *testing.T, b state.Battle, action battle.Action) actSchedule {
	t.Helper()
	schedule, err := scheduleAct(b, action)
	if err != nil {
		t.Fatalf("refused: %v", err)
	}
	return schedule
}

func armed(b state.Battle, unitID, weaponID int) *def.Weapon {
	return weaponOf(unitOf(b, unitID), weaponID)
}

func expectSchedule(t *testing.T, got, want actSchedule) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("schedule:\n got %+v\nwant %+v", got, want)
	}
}

// The guard of the actor steps aside so that the cell (1,0) is free.
func aside(units []battle.Unit) { units[squadGuardID].Pos = battle.Cell{2, 1} }

func TestScheduleAnswersAMoveAlone(t *testing.T) {
	b := squad(aside)
	step := battle.Cell{1, 0}
	expectSchedule(t, scheduled(t, b, battle.Action{ActorID: actorID, MoveTo: &step}),
		actSchedule{actorID: actorID, from: battle.Cell{0, 0}, to: step})
	expectSchedule(t, scheduled(t, b, battle.Action{ActorID: actorID}),
		actSchedule{actorID: actorID, from: battle.Cell{0, 0}, to: battle.Cell{0, 0}})
}

// Both sides name a supporter and a support defender. The support defender
// of each side takes every strike of the other side in the defend stance.
func TestScheduleAnswersEveryStrikeInTheGameOrder(t *testing.T) {
	b := squad(nil)
	got := scheduled(t, b, battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID,
			SupportAttackers: supporters(squadSupporterID), SupportDefenderID: idOf(squadGuardID)},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0),
			SupportAttackers: supporters(squadFoeSupporterID), SupportDefenderID: idOf(squadFoeGuardID)}})
	expectSchedule(t, got, actSchedule{actorID: actorID, from: battle.Cell{0, 0}, to: battle.Cell{0, 0},
		strikes: []strike{
			{segment: battle.SegmentAttackerSupport, ownerID: actorID, shooterID: squadSupporterID,
				weaponID: 0, weapon: armed(b, squadSupporterID, 0), aimedID: targetID,
				struckID: squadFoeGuardID, stance: battle.StanceDefend},
			{segment: battle.SegmentMain, ownerID: actorID, shooterID: actorID,
				weaponID: 0, weapon: armed(b, actorID, 0), aimedID: targetID,
				struckID: squadFoeGuardID, stance: battle.StanceDefend},
			{segment: battle.SegmentDefenderSupport, ownerID: targetID, shooterID: squadFoeSupporterID,
				weaponID: 0, weapon: armed(b, squadFoeSupporterID, 0), aimedID: actorID,
				struckID: squadGuardID, stance: battle.StanceDefend},
			{segment: battle.SegmentCounter, ownerID: targetID, shooterID: targetID,
				weaponID: 0, weapon: armed(b, targetID, 0), aimedID: actorID,
				struckID: squadGuardID, stance: battle.StanceDefend},
		}})
}

// With no support defender the target takes the strikes in its own stance,
// and its dodge reaches every strike of the attacker side. The stated
// behavior rides on the strike it belongs to.
func TestScheduleReadsTheStanceOfTheTargetAndTheStatedBehavior(t *testing.T) {
	b := squad(aside)
	step := battle.Cell{1, 0}
	miss := battle.Stated{}
	got := scheduled(t, b, battle.Action{ActorID: actorID, MoveTo: &step,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: &miss,
			SupportAttackers: supporters(squadSupporterID)},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceDodge}})
	expectSchedule(t, got, actSchedule{actorID: actorID, from: battle.Cell{0, 0}, to: step,
		strikes: []strike{
			{segment: battle.SegmentAttackerSupport, ownerID: actorID, shooterID: squadSupporterID,
				weaponID: 0, weapon: armed(b, squadSupporterID, 0), aimedID: targetID, dodging: true,
				struckID: targetID, stance: battle.StanceDodge},
			{segment: battle.SegmentMain, ownerID: actorID, shooterID: actorID,
				weaponID: 0, weapon: armed(b, actorID, 0), aimedID: targetID, dodging: true,
				struckID: targetID, stance: battle.StanceDodge, stated: &miss},
		}})
}
