package main

import (
	"fmt"
	"os"

	"github.com/DeanXu2357/ggge_ai/engine/server"
)

func main() {
	if err := server.New().Serve(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
