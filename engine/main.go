package main

import (
	"fmt"
	"os"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/server"
)

func openBoard(seed int64) battle.Board {
	return board.New(seed)
}

func main() {
	if err := server.New(openBoard).Serve(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
