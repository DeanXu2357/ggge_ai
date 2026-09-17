package system

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestAStatThatNoLineTouchesKeepsItsFraction(t *testing.T) {
	assert.Equal(t, 4200.5, scaled(4200.5, 0))
	assert.Equal(t, 4830.0, scaled(4200.5, 15), "a touched stat is floored after the one multiplication")
}
