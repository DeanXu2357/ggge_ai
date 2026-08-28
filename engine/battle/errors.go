package battle

import "errors"

var (
	ErrNoUnit    = errors.New("the board holds no such unit")
	ErrDestroyed = errors.New("the unit is destroyed")
	ErrOffPhase  = errors.New("the unit is not of the current phase")
	ErrActed     = errors.New("the unit acted in this turn")

	ErrIllegalAction = errors.New("the action is not legal")
	ErrIllegalMove   = errors.New("the move is not legal")
)
