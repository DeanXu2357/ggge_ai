package formula

import (
	"testing"
)

const beam = 1800.0

func fighter() Side {
	return Side{
		PilotAttack:   220,
		PilotDefense:  190,
		PilotReaction: 205,
		MechAttack:    4200,
		MechDefense:   3900,
		Mobility:      310,
	}
}

func TestTheDamageOfOneShotReadsTheDefenseAndTheBonuses(t *testing.T) {
	attacker, defender := fighter(), fighter()

	plain := StrikeDamage(beam, attacker, defender, NoTerrainCorrection, 0, 0,
		NoDefenseMultiplier)
	defended := StrikeDamage(beam, attacker, defender, NoTerrainCorrection, 0, 0,
		DefendMultiplier)
	broken := StrikeDamage(beam, attacker, defender, NoTerrainCorrection, 0.2, 0,
		NoDefenseMultiplier)

	if plain <= 0 || defended <= 0 {
		t.Fatalf("damage: %d %d", plain, defended)
	}
	if defended >= plain {
		t.Fatalf("a defended shot takes less: %d against %d", defended, plain)
	}
	if broken <= plain {
		t.Fatalf("a bonus of 0.2 raises the damage: %d against %d", broken, plain)
	}
}

func TestTheDamageRoundsAHalfToTheEvenInteger(t *testing.T) {
	blank := Side{}
	scale := CombatBaseDamage(1, blank, blank, NoTerrainCorrection)
	low := 2.5 / scale
	high := 3.5 / scale

	raw := ExpectedDamage(low, blank, blank, NoTerrainCorrection, 0, 0, NoDefenseMultiplier)
	if raw != 2.5 {
		t.Fatalf("the constructed value is %v, and the test needs a half", raw)
	}
	if got := StrikeDamage(low, blank, blank, NoTerrainCorrection, 0, 0,
		NoDefenseMultiplier); got != 2 {
		t.Fatalf("2.5 rounds to 2, not to %d", got)
	}
	if got := StrikeDamage(high, blank, blank, NoTerrainCorrection, 0, 0,
		NoDefenseMultiplier); got != 4 {
		t.Fatalf("3.5 rounds to 4, not to %d", got)
	}
}

func TestTheDodgeOfTheDefenderCostsTheAttackerItsHitRate(t *testing.T) {
	attacker, defender := fighter(), fighter()
	accuracy := 5.0

	plain := StrikeHitProbability(accuracy, attacker, defender, 0, false)
	dodged := StrikeHitProbability(accuracy, attacker, defender, 0, true)

	if plain != HitProbability(accuracy, attacker, defender, 0) {
		t.Fatalf("a shot that meets no dodge carries no correction: %v", plain)
	}
	if dodged != HitProbability(accuracy, attacker, defender, -DodgeHitPenalty) {
		t.Fatalf("a dodge takes the penalty of the rules off the rate: %v", dodged)
	}
}
