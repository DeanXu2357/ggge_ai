package battle

import (
	"fmt"
	"math/rand/v2"
)

type Node int

const (
	NodeAttackerSupport Node = iota
	NodeDefenderSupport
	NodeStrike
	NodeCounter
)

// The probability comes in with the node, so an implementation that draws
// needs no second computation of the hit rate. Covers answers whether the
// dice can settle that many nodes; the board asks before the first write.
type Dice interface {
	Lands(node Node, probability float64) bool
	Covers(draws int) bool
}

type Forced struct {
	AttackerSupport bool
	DefenderSupport bool
	Strike          bool
	Counter         bool
}

func (f Forced) Lands(node Node, _ float64) bool {
	switch node {
	case NodeAttackerSupport:
		return f.AttackerSupport
	case NodeDefenderSupport:
		return f.DefenderSupport
	case NodeStrike:
		return f.Strike
	case NodeCounter:
		return f.Counter
	}
	return false
}

func (f Forced) Covers(int) bool {
	return true
}

type ManualRoll struct {
	outcomes []bool
	next     int
}

func NewManualRoll(outcomes []bool) *ManualRoll {
	return &ManualRoll{outcomes: outcomes}
}

func (m *ManualRoll) Lands(_ Node, _ float64) bool {
	landed := m.outcomes[m.next]
	m.next++
	return landed
}

func (m *ManualRoll) Covers(draws int) bool {
	return draws <= len(m.outcomes)
}

type ServerDraw struct {
	draw *rand.Rand
}

func NewServerDraw(seed int64) *ServerDraw {
	return &ServerDraw{draw: rand.New(rand.NewPCG(uint64(seed), 0))}
}

func (d *ServerDraw) Lands(_ Node, probability float64) bool {
	return d.draw.Float64() < probability
}

func (d *ServerDraw) Covers(int) bool {
	return true
}

func DecodeOutcomes(labels []string) ([]bool, error) {
	out := make([]bool, 0, len(labels))
	for index, label := range labels {
		switch label {
		case "hit":
			out = append(out, true)
		case "miss":
			out = append(out, false)
		default:
			return nil, fmt.Errorf("outcome %d is %q, and the contract holds 'hit' and 'miss'", index, label)
		}
	}
	return out, nil
}
