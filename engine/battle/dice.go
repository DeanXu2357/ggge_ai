package battle

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
