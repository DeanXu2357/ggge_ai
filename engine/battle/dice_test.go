package battle

import (
	"reflect"
	"testing"
)

func TestManualRollReadsTheOutcomesInOrder(t *testing.T) {
	roll := NewManualRoll([]bool{true, false})

	if !roll.Lands(NodeStrike, 0.5) || roll.Lands(NodeCounter, 0.5) {
		t.Fatal("the two outcomes must come back in order")
	}
}

func TestManualRollCoversNoMoreDrawsThanItHoldsLabels(t *testing.T) {
	roll := NewManualRoll([]bool{true, false})

	if !roll.Covers(0) || !roll.Covers(2) {
		t.Fatal("two labels cover two draws")
	}
	if roll.Covers(3) {
		t.Fatal("two labels cover no third draw")
	}
}

func TestTheDrawnDiceCoverEveryNumberOfDraws(t *testing.T) {
	if !NewServerDraw(1).Covers(4) || !(Forced{}).Covers(4) {
		t.Fatal("a dice that draws its own outcome needs no label")
	}
}

func TestOneSeedGivesOneSequence(t *testing.T) {
	first, second := NewServerDraw(42), NewServerDraw(42)
	for i := 0; i < 64; i++ {
		if first.Lands(NodeStrike, 0.5) != second.Lands(NodeStrike, 0.5) {
			t.Fatalf("draw %d differs", i)
		}
	}
}

func TestTheDrawFollowsTheProbability(t *testing.T) {
	draw := NewServerDraw(7)
	if draw.Lands(NodeStrike, 0) {
		t.Fatal("probability 0 must miss")
	}
	if !draw.Lands(NodeStrike, 1) {
		t.Fatal("probability 1 must land")
	}
}

func TestOutcomesReadHitAndMissOnly(t *testing.T) {
	got, err := DecodeOutcomes([]string{"hit", "miss", "hit"})
	if err != nil || !reflect.DeepEqual(got, []bool{true, false, true}) {
		t.Fatalf("%v %v", got, err)
	}
	if _, err := DecodeOutcomes([]string{"true"}); err == nil {
		t.Fatal("an outcome outside the two labels must fail")
	}
}
