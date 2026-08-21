package battle

// A Node is one chance point of one engagement.
//
// The defender volley reads NodeSupportVolley, the same node as the attacker
// volley: the oracle 'src/ggge_ai/sandbox/model.py' settles both volleys with
// the one field 'support_hit', and one engagement never holds both.
type Node int

const (
	NodeSupportVolley Node = iota
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
	SupportVolley bool
	Strike        bool
	Counter       bool
}

func (f Forced) Lands(node Node, _ float64) bool {
	switch node {
	case NodeSupportVolley:
		return f.SupportVolley
	case NodeStrike:
		return f.Strike
	case NodeCounter:
		return f.Counter
	}
	return false
}
