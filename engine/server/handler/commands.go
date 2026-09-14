package handler

import "github.com/DeanXu2357/ggge_ai/engine/battle"

// The board holds the random source of the session, so the board is opened
// with the seed of 'init' or 'load' and not before.
type Commands struct {
	open    func(seed int64) battle.Board
	board   battle.Board
	session *session
}

func NewCommands(open func(seed int64) battle.Board) *Commands {
	return &Commands{open: open}
}
