package battle

// A Node is one chance point of one engagement. The support attack of the
// attacking side and the support attack of the defending side are two nodes,
// because one engagement holds both.
type Node int

const (
	NodeAttackerSupport Node = iota
	NodeDefenderSupport
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
