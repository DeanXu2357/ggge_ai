package battle

import "slices"

// A stage event is one scripted change of the stage. The table comes with
// 'init'; the state carries the events that wait and the events that fired.

type TriggerKind string

const (
	TriggerKill      TriggerKind = "kill"
	TriggerTurnStart TriggerKind = "turn_start"
)

type EffectKind string

const (
	EffectSpawn  EffectKind = "spawn"
	EffectWeaken EffectKind = "weaken"
)

// Trigger says when one event fires. A kill trigger with a turn limit expires
// at the start of the turn after the limit: it neither fires nor waits again.
type Trigger struct {
	Kind       TriggerKind
	UnitID     string
	WithinTurn *int
	Turn       int
}

// Effect says what one event does. A spawn puts units on the board, and a
// weaken scales the attack and the defense of the mech of each named unit.
type Effect struct {
	Kind              EffectKind
	Units             []Unit
	UnitIDs           []string
	AttackMultiplier  float64
	DefenseMultiplier float64
}

type StageEvent struct {
	ID      string
	Trigger Trigger
	Effect  Effect
}

type EventTable map[string]StageEvent

// eventsAfterAct fires every waiting kill event whose victim is gone. A victim
// that the board never held counts as gone, as the oracle counts it.
func (b *Board) eventsAfterAct() []string {
	var fired []string
	for _, id := range slices.Clone(b.PendingEvents) {
		event, known := b.Events[id]
		if !known || event.Trigger.Kind != TriggerKill || b.pastLimit(event.Trigger) {
			continue
		}
		victim := b.Unit(event.Trigger.UnitID)
		if victim == nil || !victim.Alive() {
			b.fireEvent(event)
			fired = append(fired, event.ID)
		}
	}
	return fired
}

// eventsOnNewTurn runs at the start of a turn, before the phase of the turn
// starts. A turn-start event fires, and a kill event past its turn limit leaves
// the waiting list without firing.
func (b *Board) eventsOnNewTurn() []string {
	var fired []string
	for _, id := range slices.Clone(b.PendingEvents) {
		event, known := b.Events[id]
		if !known {
			continue
		}
		switch event.Trigger.Kind {
		case TriggerTurnStart:
			if b.Turn >= event.Trigger.Turn {
				b.fireEvent(event)
				fired = append(fired, event.ID)
			}
		case TriggerKill:
			if b.pastLimit(event.Trigger) {
				b.PendingEvents = withoutEvent(b.PendingEvents, id)
			}
		}
	}
	return fired
}

func (b *Board) pastLimit(trigger Trigger) bool {
	return trigger.WithinTurn != nil && b.Turn > *trigger.WithinTurn
}

func (b *Board) fireEvent(event StageEvent) {
	b.applyEffect(event.Effect)
	b.PendingEvents = withoutEvent(b.PendingEvents, event.ID)
	b.FiredEvents = append(b.FiredEvents, event.ID)
}

func (b *Board) applyEffect(effect Effect) {
	switch effect.Kind {
	case EffectSpawn:
		b.spawn(effect.Units)
	case EffectWeaken:
		b.weaken(effect)
	}
}

// A spawn skips an id that the board already holds. The board keeps a destroyed
// unit with no hit points left, so a spawn never brings one back.
func (b *Board) spawn(templates []Unit) {
	for _, template := range templates {
		if b.Unit(template.ID) == nil {
			b.Units = append(b.Units, template.Clone())
		}
	}
}

func (b *Board) weaken(effect Effect) {
	for _, id := range effect.UnitIDs {
		unit := b.Unit(id)
		if unit == nil {
			continue
		}
		unit.Mech.Attack *= effect.AttackMultiplier
		unit.Mech.Defense *= effect.DefenseMultiplier
	}
}

func withoutEvent(ids []string, drop string) []string {
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		if id != drop {
			out = append(out, id)
		}
	}
	return out
}
