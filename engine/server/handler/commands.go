package handler

import "github.com/DeanXu2357/ggge_ai/engine/battle"

type Commands struct {
	board   battle.Board
	session *session
}

func NewCommands(b battle.Board) *Commands {
	return &Commands{board: b}
}
