package formula

import (
	"testing"
)

func TestTheDefenseMultiplierOfEveryDefense(t *testing.T) {
	if got := DefenseMultiplier(true, false); got != DefendMultiplier {
		t.Errorf("a defender with no shield pays one cut: %v", got)
	}
	if got := DefenseMultiplier(true, true); got != ShieldMultiplier*DefendMultiplier {
		t.Errorf("a defender that carries a shield pays both cuts: %v", got)
	}
	if got := DefenseMultiplier(false, false); got != NoDefenseMultiplier {
		t.Errorf("a unit that does not defend pays nothing: %v", got)
	}
	if got := DefenseMultiplier(false, true); got != NoDefenseMultiplier {
		t.Errorf("a shield answers no dodge: %v", got)
	}
}
