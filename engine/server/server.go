package server

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
	"github.com/DeanXu2357/ggge_ai/engine/server/handler"
)

// A state snapshot is bigger than the default 64 KiB line limit of the scanner.
const maxLineBytes = 16 << 20

type command func(id string, payload json.RawMessage) protocol.Response

type Server struct {
	handlers map[string]command
	commands *handler.Commands
}

func New() *Server {
	server := &Server{
		handlers: make(map[string]command, len(registry)),
		commands: handler.NewCommands(),
	}
	for name, bind := range registry {
		server.handle(name, bind(server))
	}
	return server
}

func (s *Server) handle(name string, fn command) {
	s.handlers[name] = fn
}

func (s *Server) Serve(in io.Reader, out io.Writer) error {
	scanner := bufio.NewScanner(in)
	scanner.Buffer(make([]byte, 0, bufio.MaxScanTokenSize), maxLineBytes)
	writer := bufio.NewWriter(out)
	for scanner.Scan() {
		if err := json.NewEncoder(writer).Encode(s.dispatch(scanner.Bytes())); err != nil {
			return err
		}
		if err := writer.Flush(); err != nil {
			return err
		}
	}
	return scanner.Err()
}

func (s *Server) dispatch(line []byte) protocol.Response {
	var request protocol.Request
	if err := json.Unmarshal(line, &request); err != nil {
		return protocol.Fail("", protocol.CodeBadRequest, err.Error())
	}
	if run, ok := s.handlers[request.Cmd]; ok {
		return run(request.ID, payloadOf(request))
	}
	if protocol.IsDeclared(request.Cmd) {
		return protocol.Fail(request.ID, protocol.CodeNotImplemented,
			fmt.Sprintf("command %q is declared, and its issue is not merged", request.Cmd))
	}
	return protocol.Fail(request.ID, protocol.CodeUnknownCommand,
		fmt.Sprintf("command %q is not in the contract", request.Cmd))
}

func payloadOf(request protocol.Request) json.RawMessage {
	if len(request.Payload) == 0 {
		return json.RawMessage("{}")
	}
	return request.Payload
}

func (s *Server) hello(id string, _ json.RawMessage) protocol.Response {
	commands := make([]protocol.Command, 0, len(protocol.Declared))
	for _, name := range protocol.Declared {
		_, implemented := s.handlers[name]
		commands = append(commands, protocol.Command{Name: name, Implemented: implemented})
	}
	return protocol.Ok(id, protocol.HelloPayload{Protocol: protocol.Version, Commands: commands})
}

func ping(id string, _ json.RawMessage) protocol.Response {
	return protocol.Ok(id, protocol.PingResponse{})
}
