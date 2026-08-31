package handler

import "github.com/DeanXu2357/ggge_ai/engine/battle"

type Commands struct {
	factory battle.BoardFactory
	session *session
}

func NewCommands(factory battle.BoardFactory) *Commands {
	return &Commands{factory: factory}
}
