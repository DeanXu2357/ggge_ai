// Package protocol holds the envelope, the command list, and the types of
// the battle engine contract (docs/spec/battle-engine-protocol.md).
package protocol

import "encoding/json"

const Version = "1.2"

const (
	CodeUnknownCommand = "unknown_command"
	CodeNotImplemented = "not_implemented"
	CodeBadRequest     = "bad_request"
	CodeNoSession      = "no_session"
	CodeIllegalState   = "illegal_state"
	CodeIllegalAction  = "illegal_action"
	CodeEmptyHistory   = "empty_history"
)

type Request struct {
	ID      string          `json:"id"`
	Cmd     string          `json:"cmd"`
	Payload json.RawMessage `json:"payload,omitempty"`
}

type Response struct {
	ID      string `json:"id"`
	OK      bool   `json:"ok"`
	Payload any    `json:"payload,omitempty"`
	Error   *Error `json:"error,omitempty"`
}

type Error struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func Ok(id string, payload any) Response {
	return Response{ID: id, OK: true, Payload: payload}
}

func Fail(id string, code string, message string) Response {
	return Response{ID: id, OK: false, Error: &Error{Code: code, Message: message}}
}
