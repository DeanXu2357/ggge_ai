package battle

import "testing"

func TestTheScriptedDiceReadsOneOutcomeForEachNodeInOrder(t *testing.T) {
	dice := NewScripted([]bool{true, false, true})

	got := []bool{
		dice.Lands(NodeSupportVolley, 0),
		dice.Lands(NodeStrike, 1),
		dice.Lands(NodeCounter, 0),
	}

	if got[0] != true || got[1] != false || got[2] != true {
		t.Fatalf("outcomes: %v", got)
	}
	if dice.Short() {
		t.Fatal("the list held one outcome for each node")
	}
}

func TestTheScriptedDiceReportsAShortList(t *testing.T) {
	dice := NewScripted([]bool{true})

	dice.Lands(NodeStrike, 1)
	if dice.Short() {
		t.Fatal("the first node read the one outcome of the list")
	}
	dice.Lands(NodeCounter, 1)

	if !dice.Short() {
		t.Fatal("the second node found no outcome")
	}
}

func TestOneSeedGivesOneStreamOfOutcomes(t *testing.T) {
	first := draws(NewSampled(7), 40)
	second := draws(NewSampled(7), 40)
	other := draws(NewSampled(8), 40)

	if first != second {
		t.Fatalf("one seed gave two streams:\n%s\n%s", first, second)
	}
	if first == other {
		t.Fatal("two seeds gave one stream")
	}
}

func TestACloneOfTheSampledDiceKeepsThePlaceOfTheStream(t *testing.T) {
	source := NewSampled(11)
	source.Lands(NodeStrike, 0.5)

	branch := source.Clone()
	after := draws(source, 20)

	if got := draws(branch, 20); got != after {
		t.Fatalf("the clone parted from the source:\n%s\n%s", got, after)
	}
}

func TestASampledNodeReadsItsProbability(t *testing.T) {
	source := NewSampled(3)

	for range 100 {
		if source.Lands(NodeStrike, 0) {
			t.Fatal("a node of probability 0 landed")
		}
		if !source.Lands(NodeStrike, 1) {
			t.Fatal("a node of probability 1 missed")
		}
	}
}

func draws(dice *Sampled, count int) string {
	out := make([]byte, 0, count)
	for range count {
		if dice.Lands(NodeStrike, 0.5) {
			out = append(out, 'h')
			continue
		}
		out = append(out, 'm')
	}
	return string(out)
}
