package system

import (
	"errors"
	"math/rand/v2"
	"reflect"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func draw() *rand.Rand {
	return rand.New(rand.NewPCG(7, 0))
}

func none() *battle.ResponseAttack {
	return &battle.ResponseAttack{Stance: battle.StanceNone}
}

func plainAttack() *battle.Attack {
	return &battle.Attack{WeaponID: 0, TargetID: targetID}
}

func withMoveRange(unit battle.Unit, moveRange int) battle.Unit {
	unit.Mech.MoveRange = moveRange
	return unit
}

// refused asserts that Commit answers the sentinel and writes nothing.
func refused(t *testing.T, b state.Battle, action battle.Action, sentinel error) {
	t.Helper()
	before := b.Values.Clone()
	_, events, err := Commit(b, action, draw())
	if !errors.Is(err, sentinel) {
		t.Fatalf("error: %v, want %v", err, sentinel)
	}
	if events != nil {
		t.Fatalf("a refusal carries no event: %+v", events)
	}
	if !reflect.DeepEqual(before, *b.Values) {
		t.Fatalf("the refusal wrote the column:\n%+v\n%+v", before, *b.Values)
	}
}

func accepted(t *testing.T, b state.Battle, action battle.Action) (state.Values, []battle.Event) {
	t.Helper()
	values, events, err := Commit(b, action, draw())
	if err != nil {
		t.Fatalf("refused: %v", err)
	}
	return values, events
}

func TestCommitAcceptsAPlainAttack(t *testing.T) {
	accepted(t, shootout(), battle.Action{ActorID: actorID, Attack: plainAttack(), ResponseAttack: none()})
}

func TestCommitReadsTheActionByPresence(t *testing.T) {
	for name, action := range map[string]battle.Action{
		"an attack with no response":    {ActorID: actorID, Attack: plainAttack()},
		"a response with no attack":     {ActorID: actorID, ResponseAttack: none()},
		"an attack beside a map attack": {ActorID: actorID, Attack: plainAttack(), ResponseAttack: none(), MapAttack: &battle.MapAttack{}},
		"a map attack":                  {ActorID: actorID, MapAttack: &battle.MapAttack{}},
	} {
		t.Run(name, func(t *testing.T) {
			refused(t, shootout(), action, battle.ErrIllegalAction)
		})
	}
	accepted(t, shootout(), battle.Action{ActorID: actorID})
}

func TestCommitRefusesAUnitThatCannotAct(t *testing.T) {
	acted := fighter(battle.FactionAlly, battle.Cell{0, 0})
	acted.Acted = true
	wreck := fighter(battle.FactionAlly, battle.Cell{0, 1})
	wreck.HP = 0
	b := board(acted, fighter(battle.FactionEnemy, battle.Cell{3, 0}), wreck)

	refused(t, b, battle.Action{ActorID: actorID}, battle.ErrActed)
	refused(t, b, battle.Action{ActorID: targetID}, battle.ErrOffPhase)
	refused(t, b, battle.Action{ActorID: 2}, battle.ErrDestroyed)
	refused(t, b, battle.Action{ActorID: 9}, battle.ErrNoUnit)
}

func TestCommitChecksTheTargetAndTheWeaponOfTheAttacker(t *testing.T) {
	actor := fighter(battle.FactionAlly, battle.Cell{0, 0})
	actor.Mech.Weapons = []battle.Weapon{beam()}
	target := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	far := fighter(battle.FactionEnemy, battle.Cell{4, 0})
	dead := target
	dead.HP = 0
	drained := actor
	drained.EN = 5
	friend := fighter(battle.FactionAlly, battle.Cell{3, 0})

	for name, tc := range map[string]struct {
		board    state.Battle
		weaponID int
		targetID int
		sentinel error
	}{
		"a target that names nothing":      {board(actor, target), 0, 9, battle.ErrNoUnit},
		"a target that is no foe":          {board(actor, friend), 0, targetID, battle.ErrIllegalAction},
		"a target that is destroyed":       {board(actor, dead), 0, targetID, battle.ErrDestroyed},
		"a weapon that does not reach":     {board(actor, far), 0, targetID, battle.ErrIllegalAction},
		"a weapon the unit cannot pay":     {board(drained, target), 0, targetID, battle.ErrIllegalAction},
		"a weapon the unit does not carry": {board(actor, target), 3, targetID, battle.ErrIllegalAction},
	} {
		t.Run(name, func(t *testing.T) {
			refused(t, tc.board, battle.Action{ActorID: actorID,
				Attack: &battle.Attack{WeaponID: tc.weaponID, TargetID: tc.targetID}, ResponseAttack: none()},
				tc.sentinel)
		})
	}
}

func TestCommitChecksTheMoveBeforeTheStrike(t *testing.T) {
	actor := withMoveRange(fighter(battle.FactionAlly, battle.Cell{0, 0}), 1)
	fixed := beam()
	fixed.UsableAfterMove = false
	actor.Mech.Weapons = []battle.Weapon{beam(), fixed}
	target := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	units := []battle.Unit{actor, target}
	step := battle.Cell{1, 0}
	leap := battle.Cell{2, 0}

	accepted(t, board(units...), battle.Action{ActorID: actorID, MoveTo: &step,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID}, ResponseAttack: none()})
	refused(t, board(units...), battle.Action{ActorID: actorID, MoveTo: &step,
		Attack: &battle.Attack{WeaponID: 1, TargetID: targetID}, ResponseAttack: none()}, battle.ErrIllegalMove)
	refused(t, board(units...), battle.Action{ActorID: actorID, MoveTo: &leap}, battle.ErrIllegalMove)
	accepted(t, board(units...), battle.Action{ActorID: actorID, MoveTo: &step})
}

func TestCommitReadsTheReachFromTheCellAfterTheMove(t *testing.T) {
	actor := withMoveRange(fighter(battle.FactionAlly, battle.Cell{0, 0}), 1)
	actor.Mech.Weapons = []battle.Weapon{beam()}
	target := fighter(battle.FactionEnemy, battle.Cell{4, 0})
	step := battle.Cell{1, 0}

	refused(t, board(actor, target), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID}, ResponseAttack: none()}, battle.ErrIllegalAction)
	accepted(t, board(actor, target), battle.Action{ActorID: actorID, MoveTo: &step,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID}, ResponseAttack: none()})
}

func TestCommitChecksTheStanceAndTheCounterWeaponOfTheDefender(t *testing.T) {
	short := rifle("short", 1, 2)
	short.ENCost = 10
	actor := withMoveRange(fighter(battle.FactionAlly, battle.Cell{0, 0}), 1)
	actor.Mech.Weapons = []battle.Weapon{beam()}
	target := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	target.Mech.Weapons = []battle.Weapon{short}
	broke := target
	broke.EN = 5
	step := battle.Cell{1, 0}

	for name, tc := range map[string]struct {
		board    state.Battle
		moveTo   *battle.Cell
		response battle.ResponseAttack
		sentinel error
	}{
		"a counter with no weapon": {board(actor, target), nil,
			battle.ResponseAttack{Stance: battle.StanceCounter}, battle.ErrIllegalAction},
		"a dodge that fires a weapon": {board(actor, target), nil,
			battle.ResponseAttack{Stance: battle.StanceDodge, WeaponID: idOf(0)}, battle.ErrIllegalAction},
		"a stance outside the contract": {board(actor, target), nil,
			battle.ResponseAttack{Stance: "shield"}, battle.ErrIllegalAction},
		"a counter weapon that does not reach": {board(actor, target), nil,
			battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0)}, battle.ErrIllegalAction},
		"a counter weapon the defender cannot pay": {board(actor, broke), &step,
			battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0)}, battle.ErrIllegalAction},
		"a counter weapon the defender does not carry": {board(actor, target), &step,
			battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(1)}, battle.ErrIllegalAction},
	} {
		t.Run(name, func(t *testing.T) {
			response := tc.response
			refused(t, tc.board, battle.Action{ActorID: actorID, MoveTo: tc.moveTo,
				Attack: &battle.Attack{WeaponID: 0, TargetID: targetID}, ResponseAttack: &response}, tc.sentinel)
		})
	}
	accepted(t, board(actor, target), battle.Action{ActorID: actorID, MoveTo: &step,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0)}})
}

const (
	squadSupporterID    = 2
	squadFoeSupporterID = 3
	squadFoeGuardID     = 4
	squadGuardID        = 5
	squadSecondID       = 6
	squadThirdID        = 7
	squadFourthID       = 8
)

func longRifle() battle.Weapon {
	out := rifle("long", 1, 5)
	out.ENCost = 10
	return out
}

func squadUnit(faction battle.Faction, cell battle.Cell) battle.Unit {
	out := withMoveRange(fighter(faction, cell), 2)
	out.Mech.Weapons = []battle.Weapon{longRifle(), beam()}
	out.SupportAttackCharges, out.SupportDefendCharges = 1, 1
	return out
}

// The squad stands the actor at (0,0) with a beam of reach 3 and the target
// at (3,0). Every other unit carries a long rifle of reach 5, one support
// attack charge and one support defend charge, and a move range of 2.
func squadUnits() []battle.Unit {
	actor := withMoveRange(fighter(battle.FactionAlly, battle.Cell{0, 0}), 1)
	actor.Mech.Weapons = []battle.Weapon{beam()}
	target := squadUnit(battle.FactionEnemy, battle.Cell{3, 0})
	return []battle.Unit{
		actor, target,
		squadUnit(battle.FactionAlly, battle.Cell{0, 1}),
		squadUnit(battle.FactionEnemy, battle.Cell{3, 1}),
		squadUnit(battle.FactionEnemy, battle.Cell{4, 0}),
		squadUnit(battle.FactionAlly, battle.Cell{1, 0}),
		squadUnit(battle.FactionAlly, battle.Cell{1, 1}),
		squadUnit(battle.FactionAlly, battle.Cell{0, 2}),
		squadUnit(battle.FactionAlly, battle.Cell{2, 0}),
	}
}

func squad(edit func(units []battle.Unit)) state.Battle {
	units := squadUnits()
	if edit != nil {
		edit(units)
	}
	return board(units...)
}

func supporters(ids ...int) []battle.SupportAttacker {
	out := make([]battle.SupportAttacker, 0, len(ids))
	for _, id := range ids {
		out = append(out, battle.SupportAttacker{UnitID: id, WeaponID: 0})
	}
	return out
}

func TestCommitAcceptsTheSupportUnitsOfBothSides(t *testing.T) {
	accepted(t, squad(nil), battle.Action{ActorID: actorID,
		Attack: &battle.Attack{WeaponID: 0, TargetID: targetID,
			SupportAttackers: supporters(squadSupporterID), SupportDefenderID: idOf(squadGuardID)},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0),
			SupportAttackers: supporters(squadFoeSupporterID), SupportDefenderID: idOf(squadFoeGuardID)}})
}

func TestCommitChecksEverySupporter(t *testing.T) {
	illegal := battle.ErrIllegalAction
	for name, tc := range map[string]struct {
		edit       func(units []battle.Unit)
		supporters []battle.SupportAttacker
		sentinel   error
	}{
		"a supporter with no charge":            {func(u []battle.Unit) { u[squadSupporterID].SupportAttackCharges = 0 }, supporters(squadSupporterID), illegal},
		"a supporter out of its move range":     {func(u []battle.Unit) { u[squadSupporterID].Mech.MoveRange = 0 }, supporters(squadSupporterID), illegal},
		"a supporter that cannot pay":           {func(u []battle.Unit) { u[squadSupporterID].EN = 5 }, supporters(squadSupporterID), illegal},
		"a supporter that is destroyed":         {func(u []battle.Unit) { u[squadSupporterID].HP = 0 }, supporters(squadSupporterID), battle.ErrDestroyed},
		"a weapon that does not reach the foe":  {nil, []battle.SupportAttacker{{UnitID: squadSupporterID, WeaponID: 1}}, illegal},
		"a weapon the supporter does not carry": {nil, []battle.SupportAttacker{{UnitID: squadSupporterID, WeaponID: 2}}, illegal},
		"a supporter of the other side":         {nil, supporters(squadFoeSupporterID), illegal},
		"the actor as its own supporter":        {nil, supporters(actorID), illegal},
		"a supporter named twice":               {nil, supporters(squadSupporterID, squadSupporterID), illegal},
		"more supporters than the cap":          {nil, supporters(squadSupporterID, squadSecondID, squadThirdID, squadFourthID), illegal},
		"a supporter that names nothing":        {nil, supporters(9), battle.ErrNoUnit},
	} {
		t.Run(name, func(t *testing.T) {
			refused(t, squad(tc.edit), battle.Action{ActorID: actorID,
				Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, SupportAttackers: tc.supporters},
				ResponseAttack: none()}, tc.sentinel)
		})
	}
	accepted(t, squad(nil), battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, SupportAttackers: supporters(squadSupporterID, squadSecondID, squadThirdID)},
		ResponseAttack: none()})
}

func TestCommitChecksTheSupportersOfTheDefenderAgainstTheCellAfterTheMove(t *testing.T) {
	step := battle.Cell{1, 0}
	clear := func(u []battle.Unit) { u[squadGuardID].Pos = battle.Cell{2, 1} }
	foeBeam := []battle.SupportAttacker{{UnitID: squadFoeSupporterID, WeaponID: 1}}

	refused(t, squad(clear), battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone, SupportAttackers: foeBeam}},
		battle.ErrIllegalAction)
	accepted(t, squad(clear), battle.Action{ActorID: actorID, MoveTo: &step,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone, SupportAttackers: foeBeam}})
	refused(t, squad(clear), battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID},
		ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone, SupportAttackers: supporters(squadSupporterID)}},
		battle.ErrIllegalAction)
}

func TestCommitChecksTheSupportDefenderOfEachSide(t *testing.T) {
	illegal := battle.ErrIllegalAction
	for name, tc := range map[string]struct {
		edit     func(units []battle.Unit)
		guard    *int
		foeGuard *int
		stance   battle.Stance
		sentinel error
	}{
		"a support defender with no charge":        {func(u []battle.Unit) { u[squadGuardID].SupportDefendCharges = 0 }, idOf(squadGuardID), nil, battle.StanceNone, illegal},
		"a support defender out of its move range": {func(u []battle.Unit) { u[squadGuardID].Mech.MoveRange = 0 }, idOf(squadGuardID), nil, battle.StanceNone, illegal},
		"a support defender that is destroyed":     {func(u []battle.Unit) { u[squadFoeGuardID].HP = 0 }, nil, idOf(squadFoeGuardID), battle.StanceNone, battle.ErrDestroyed},
		"a support defender of the other side":     {nil, idOf(squadFoeGuardID), nil, battle.StanceNone, illegal},
		"the actor as its own support defender":    {nil, idOf(actorID), nil, battle.StanceNone, illegal},
		"the target as its own support defender":   {nil, nil, idOf(targetID), battle.StanceNone, illegal},
		"a support defender that names nothing":    {nil, idOf(9), nil, battle.StanceNone, battle.ErrNoUnit},
		"a support defender that also supports":    {nil, idOf(squadSupporterID), nil, battle.StanceNone, illegal},
		"a defender that defends and names one":    {nil, nil, idOf(squadFoeGuardID), battle.StanceDefend, illegal},
	} {
		t.Run(name, func(t *testing.T) {
			refused(t, squad(tc.edit), battle.Action{ActorID: actorID,
				Attack: &battle.Attack{WeaponID: 0, TargetID: targetID,
					SupportAttackers: supporters(squadSupporterID), SupportDefenderID: tc.guard},
				ResponseAttack: &battle.ResponseAttack{Stance: tc.stance, SupportDefenderID: tc.foeGuard}}, tc.sentinel)
		})
	}
}

// The guard stands at (2,1), three cells from the actor of today and two
// from the cell it steps to; its move range is two.
func TestCommitChecksTheSupportDefenderOfTheActorAgainstTheCellAfterTheMove(t *testing.T) {
	step := battle.Cell{1, 0}
	aside := func(u []battle.Unit) { u[squadGuardID].Pos = battle.Cell{2, 1} }

	refused(t, squad(aside), battle.Action{ActorID: actorID,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, SupportDefenderID: idOf(squadGuardID)},
		ResponseAttack: none()}, battle.ErrIllegalAction)
	accepted(t, squad(aside), battle.Action{ActorID: actorID, MoveTo: &step,
		Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, SupportDefenderID: idOf(squadGuardID)},
		ResponseAttack: none()})
}

func beamOf(accuracy float64) battle.Weapon {
	out := beam()
	out.Accuracy = accuracy
	return out
}

func shootoutWith(weapon battle.Weapon) state.Battle {
	attacker := fighter(battle.FactionAlly, battle.Cell{0, 0})
	attacker.Mech.Weapons = []battle.Weapon{weapon}
	target := fighter(battle.FactionEnemy, battle.Cell{3, 0})
	target.Mech.Weapons = []battle.Weapon{beam()}
	return board(attacker, target)
}

// The shootout pair gives a beam of accuracy 5 a hit rate near 6 percent,
// so an accuracy of -10 clamps the rate to 0 and 200 clamps it to 100.
func TestCommitRefusesAStatedBehaviorTheRatesGiveNoChanceOf(t *testing.T) {
	for name, tc := range map[string]struct {
		accuracy float64
		stance   battle.Stance
		stated   battle.Stated
		sentinel error
	}{
		"a critical at rate 0":                 {5, battle.StanceNone, battle.Stated{Crit: true, Hit: true}, battle.ErrIllegalAction},
		"a hit at hit rate 0":                  {-10, battle.StanceNone, battle.Stated{Hit: true}, battle.ErrIllegalAction},
		"a miss at hit rate 0":                 {-10, battle.StanceNone, battle.Stated{Hit: false}, nil},
		"a miss at hit rate 1":                 {200, battle.StanceNone, battle.Stated{Hit: false}, battle.ErrIllegalAction},
		"a hit at hit rate 1":                  {200, battle.StanceNone, battle.Stated{Hit: true}, nil},
		"a miss at an uncertain rate":          {5, battle.StanceNone, battle.Stated{Hit: false}, nil},
		"a hit at an uncertain rate":           {5, battle.StanceNone, battle.Stated{Hit: true}, nil},
		"a miss the dodge of the target opens": {110, battle.StanceDodge, battle.Stated{Hit: false}, nil},
		"a miss a standing target refuses":     {110, battle.StanceNone, battle.Stated{Hit: false}, battle.ErrIllegalAction},
	} {
		t.Run(name, func(t *testing.T) {
			stated := tc.stated
			action := battle.Action{ActorID: actorID,
				Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID, Stated: &stated},
				ResponseAttack: &battle.ResponseAttack{Stance: tc.stance}}
			if tc.sentinel == nil {
				accepted(t, shootoutWith(beamOf(tc.accuracy)), action)
				return
			}
			refused(t, shootoutWith(beamOf(tc.accuracy)), action, tc.sentinel)
		})
	}
}

func TestCommitReadsTheStatedBehaviorOfEveryStrike(t *testing.T) {
	crit := battle.Stated{Crit: true, Hit: true}
	for name, action := range map[string]battle.Action{
		"a supporter of the attacker": {ActorID: actorID,
			Attack: &battle.Attack{WeaponID: 0, TargetID: targetID,
				SupportAttackers: []battle.SupportAttacker{{UnitID: squadSupporterID, WeaponID: 0, Stated: &crit}}},
			ResponseAttack: none()},
		"a supporter of the defender": {ActorID: actorID,
			Attack: &battle.Attack{WeaponID: 0, TargetID: targetID},
			ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceNone,
				SupportAttackers: []battle.SupportAttacker{{UnitID: squadFoeSupporterID, WeaponID: 0, Stated: &crit}}}},
		"the counter": {ActorID: actorID,
			Attack:         &battle.Attack{WeaponID: 0, TargetID: targetID},
			ResponseAttack: &battle.ResponseAttack{Stance: battle.StanceCounter, WeaponID: idOf(0), Stated: &crit}},
	} {
		t.Run(name, func(t *testing.T) {
			refused(t, squad(nil), action, battle.ErrIllegalAction)
		})
	}
}
