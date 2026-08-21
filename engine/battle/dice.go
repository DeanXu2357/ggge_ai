package battle

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
