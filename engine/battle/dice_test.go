package battle

import "testing"

func TestManualRollReadsTheOutcomesInOrderAndReportsAShortList(t *testing.T) {
	roll := NewManualRoll([]bool{true, false})

	if !roll.Lands(NodeStrike, 0.5) || roll.Lands(NodeCounter, 0.5) {
		t.Fatal("the two outcomes must come back in order")
	}
	if roll.Short() {
		t.Fatal("two reads of two outcomes are not short")
	}
	if roll.Lands(NodeStrike, 0.5) {
		t.Fatal("a read past the end must miss")
	}
	if !roll.Short() {
		t.Fatal("a read past the end must mark the roll short")
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

func TestACloneContinuesFromTheSamePlace(t *testing.T) {
	draw := NewServerDraw(3)
	draw.Lands(NodeStrike, 0.5)
	clone := draw.Clone()
	for i := 0; i < 32; i++ {
		if draw.Lands(NodeStrike, 0.5) != clone.Lands(NodeStrike, 0.5) {
			t.Fatalf("draw %d differs after the clone", i)
		}
	}
}

func TestACloneDoesNotMoveTheOriginal(t *testing.T) {
	draw := NewServerDraw(3)
	clone := draw.Clone()
	var fromClone, fromOriginal []bool
	for i := 0; i < 16; i++ {
		fromClone = append(fromClone, clone.Lands(NodeStrike, 0.5))
	}
	for i := 0; i < 16; i++ {
		fromOriginal = append(fromOriginal, draw.Lands(NodeStrike, 0.5))
	}
	for i := range fromClone {
		if fromClone[i] != fromOriginal[i] {
			t.Fatalf("draw %d: the original moved with the clone", i)
		}
	}
}
