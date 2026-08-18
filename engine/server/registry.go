package server

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

// A Binding builds the handler of one command against the server that holds the
// board. A port issue adds one Register call in an init function of its own
// file, and the loop needs no change.
type Binding func(*Server) Handler

var registry = map[string]Binding{}

// Register binds one declared command name to its handler. A name outside the
// contract, or a second binding of one name, stops the build at start: 'hello'
// reads this registry, and its answer must match what the loop dispatches.
func Register(name string, bind Binding) {
	if !protocol.IsDeclared(name) {
		panic(fmt.Sprintf("command %q is not in the contract", name))
	}
	if _, taken := registry[name]; taken {
		panic(fmt.Sprintf("command %q already has a handler", name))
	}
	registry[name] = bind
}

func init() {
	Register("hello", func(s *Server) Handler { return s.hello })
	Register("ping", func(*Server) Handler { return ping })
}
