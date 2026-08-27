package battle

import "math/rand/v2"

type Node int

const (
	NodeAttackerSupport Node = iota
	NodeDefenderSupport
	NodeStrike
	NodeCounter
)

// The probability comes in with the node, so an implementation that draws
// needs no second computation of the hit rate.
type Dice interface {
	Lands(node Node, probability float64) bool
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

type ManualRoll struct {
	outcomes []bool
	next     int
	short    bool
}

func NewManualRoll(outcomes []bool) *ManualRoll {
	return &ManualRoll{outcomes: outcomes}
}

func (m *ManualRoll) Lands(_ Node, _ float64) bool {
	if m.next >= len(m.outcomes) {
		m.short = true
		return false
	}
	landed := m.outcomes[m.next]
	m.next++
	return landed
}

func (m *ManualRoll) Short() bool {
	return m.short
}

type ServerDraw struct {
	source *rand.PCG
	draw   *rand.Rand
}

func NewServerDraw(seed int64) *ServerDraw {
	return newServerDraw(rand.NewPCG(uint64(seed), 0))
}

func newServerDraw(source *rand.PCG) *ServerDraw {
	return &ServerDraw{source: source, draw: rand.New(source)}
}

func (d *ServerDraw) Lands(_ Node, probability float64) bool {
	return d.draw.Float64() < probability
}

func (d *ServerDraw) Clone() *ServerDraw {
	state, err := d.source.MarshalBinary()
	if err != nil {
		panic(err)
	}
	source := rand.NewPCG(0, 0)
	if err := source.UnmarshalBinary(state); err != nil {
		panic(err)
	}
	return newServerDraw(source)
}
