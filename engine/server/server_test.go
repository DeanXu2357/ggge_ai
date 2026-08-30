package server

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

type reply struct {
	ID      string          `json:"id"`
	OK      bool            `json:"ok"`
	Payload json.RawMessage `json:"payload"`
	Error   *protocol.Error `json:"error"`
}

func serve(t *testing.T, s *Server, lines ...string) []reply {
	t.Helper()
	var out strings.Builder
	if err := s.Serve(strings.NewReader(strings.Join(lines, "\n")+"\n"), &out); err != nil {
		t.Fatalf("serve: %v", err)
	}
	var replies []reply
	decoder := json.NewDecoder(strings.NewReader(out.String()))
	for decoder.More() {
		var one reply
		if err := decoder.Decode(&one); err != nil {
			t.Fatalf("decode: %v", err)
		}
		replies = append(replies, one)
	}
	return replies
}

func TestResponseKeepsTheRequestID(t *testing.T) {
	server := New()
	server.handle("init", func(id string, _ json.RawMessage) protocol.Response {
		return protocol.Fail(id, protocol.CodeNoSession, "no board")
	})

	replies := serve(t, server, `{"id":"a1","cmd":"ping","payload":{}}`, `{"id":"a2","cmd":"init"}`)

	if len(replies) != 2 {
		t.Fatalf("replies: %d", len(replies))
	}
	if replies[0].ID != "a1" || !replies[0].OK {
		t.Fatalf("ping reply: %+v", replies[0])
	}
	if replies[1].ID != "a2" || replies[1].OK {
		t.Fatalf("failing handler reply: %+v", replies[1])
	}
	if replies[1].Error.Code != protocol.CodeNoSession {
		t.Fatalf("code: %s", replies[1].Error.Code)
	}
}

func TestHelloListsEveryDeclaredCommand(t *testing.T) {
	replies := serve(t, New(), `{"id":"h1","cmd":"hello","payload":{}}`)

	var payload protocol.HelloPayload
	if err := json.Unmarshal(replies[0].Payload, &payload); err != nil {
		t.Fatalf("payload: %v", err)
	}
	if payload.Protocol != protocol.Version {
		t.Fatalf("protocol: %s", payload.Protocol)
	}
	if len(payload.Commands) != len(protocol.Declared) {
		t.Fatalf("commands: %d", len(payload.Commands))
	}
	built := map[string]bool{
		"hello": true, "ping": true, "load": true, "reach": true,
		"actions": true, "response_attacks": true,
		"init": true, "act": true, "export": true,
	}
	for index, command := range payload.Commands {
		if command.Name != protocol.Declared[index] {
			t.Fatalf("order at %d: %s", index, command.Name)
		}
		if command.Implemented != built[command.Name] {
			t.Fatalf("%s implemented: %v", command.Name, command.Implemented)
		}
	}
}

func TestDeclaredCommandWithNoHandlerIsNotImplemented(t *testing.T) {
	replies := serve(t, New(),
		`{"id":"n1","cmd":"place","payload":{}}`,
		`{"id":"n2","cmd":"ping","payload":{}}`)

	if replies[0].OK || replies[0].ID != "n1" {
		t.Fatalf("reply: %+v", replies[0])
	}
	if replies[0].Error.Code != protocol.CodeNotImplemented {
		t.Fatalf("code: %s", replies[0].Error.Code)
	}
	if !replies[1].OK {
		t.Fatalf("the loop stopped: %+v", replies[1])
	}
}

func TestUnknownCommandIsRefused(t *testing.T) {
	replies := serve(t, New(),
		`{"id":"u1","cmd":"teleport","payload":{}}`,
		`{"id":"u2","cmd":"ping","payload":{}}`)

	if replies[0].Error.Code != protocol.CodeUnknownCommand || replies[0].ID != "u1" {
		t.Fatalf("reply: %+v", replies[0])
	}
	if !replies[1].OK {
		t.Fatalf("the loop stopped: %+v", replies[1])
	}
}

func TestMalformedLineIsBadRequestWithAnEmptyID(t *testing.T) {
	replies := serve(t, New(), `{"id":"m1",`, `{"id":"m2","cmd":"ping","payload":{}}`)

	if replies[0].OK || replies[0].ID != "" {
		t.Fatalf("reply: %+v", replies[0])
	}
	if replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("code: %s", replies[0].Error.Code)
	}
	if !replies[1].OK {
		t.Fatalf("the loop stopped: %+v", replies[1])
	}
}

func TestServeReturnsOnEOF(t *testing.T) {
	var out strings.Builder
	if err := New().Serve(strings.NewReader(""), &out); err != nil {
		t.Fatalf("serve: %v", err)
	}
	if out.String() != "" {
		t.Fatalf("output: %q", out.String())
	}
}

func TestServeReadsALineBiggerThanTheScannerDefault(t *testing.T) {
	line := `{"id":"b1","cmd":"ping","payload":{"pad":"` + strings.Repeat("x", 1<<20) + `"}}`

	replies := serve(t, New(), line)

	if !replies[0].OK || replies[0].ID != "b1" {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestTheRegistryBindsEveryCommandOfTheBuild(t *testing.T) {
	server := New()

	if _, bound := server.handlers["hello"]; !bound {
		t.Fatal("hello has no handler")
	}
	if len(server.handlers) != len(registry) {
		t.Fatalf("handlers: %d against %d", len(server.handlers), len(registry))
	}
}

func TestRegisterRefusesANameOutsideTheContract(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("a name outside the contract must stop the build")
		}
	}()

	register("teleport", func(*Server) command { return ping })
}

func TestRegisterRefusesASecondHandlerForOneName(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("a second handler for one name must stop the build")
		}
	}()

	register("ping", func(*Server) command { return ping })
}
