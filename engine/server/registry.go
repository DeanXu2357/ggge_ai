package server

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

type binding func(*Server) command

var registry = map[string]binding{}

// A name outside the contract, or a second binding of one name, stops the build
// at start: 'hello' reads this registry, and its answer must match what the loop
// dispatches.
func register(name string, bind binding) {
	if !protocol.IsDeclared(name) {
		panic(fmt.Sprintf("command %q is not in the contract", name))
	}
	if _, taken := registry[name]; taken {
		panic(fmt.Sprintf("command %q already has a handler", name))
	}
	registry[name] = bind
}

func init() {
	register("hello", func(s *Server) command { return s.hello })
	register("ping", func(*Server) command { return ping })
}
