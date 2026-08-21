package battle

import "math/rand/v2"

// A Node is one chance point of one engagement. The volley of the attacker and
// the volley of the defender are two nodes, because one engagement holds both.
type Node int

const (
	NodeSupportVolley Node = iota
	NodeDefenderVolley
	NodeStrike
	NodeCounter
)

// Dice settles the chance nodes of one resolution. The probability of the node
// comes in with the node, so an implementation that draws needs no second
// computation of the hit rate.
type Dice interface {
	Lands(node Node, probability float64) bool
}

// Forced holds the outcome of each node and reads no probability.
type Forced struct {
	SupportVolley  bool
	DefenderVolley bool
	Strike         bool
	Counter        bool
}

func (f Forced) Lands(node Node, _ float64) bool {
	switch node {
	case NodeSupportVolley:
		return f.SupportVolley
	case NodeDefenderVolley:
		return f.DefenderVolley
	case NodeStrike:
		return f.Strike
	case NodeCounter:
		return f.Counter
	}
	return false
}

// Scripted reads one outcome for each node from a list, in the order in which
// the resolution settles the nodes. The wire form of the forced dice carries
// that list (docs/spec/battle-engine-protocol.md, the command 'act').
type Scripted struct {
	outcomes []bool
	read     int
}

func NewScripted(outcomes []bool) *Scripted {
	return &Scripted{outcomes: outcomes}
}

// A node beyond the list reads as a miss, and Short reports the overrun. The
// command refuses the whole activation then, so no outcome of a short list
// reaches the board.
func (s *Scripted) Lands(_ Node, _ float64) bool {
	s.read++
	if s.read > len(s.outcomes) {
		return false
	}
	return s.outcomes[s.read-1]
}

func (s *Scripted) Short() bool {
	return s.read > len(s.outcomes)
}

// Sampled draws each node from the random source of the session. The seed of
// 'init' builds that source, so one seed and one command sequence give one
// battle. The engine holds no other random source.
type Sampled struct {
	source rand.PCG
}

func NewSampled(seed int64) *Sampled {
	out := &Sampled{}
	out.source.Seed(uint64(seed), 0)
	return out
}

// Clone gives a source at the same place of the stream. A command draws from a
// clone and installs the clone when it succeeds, so a refused command consumes
// no draw and the battle stays reproducible.
func (s *Sampled) Clone() *Sampled {
	out := *s
	return &out
}

func (s *Sampled) Lands(_ Node, probability float64) bool {
	return rand.New(&s.source).Float64() < probability
}
