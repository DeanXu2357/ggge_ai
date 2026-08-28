// Package handler holds the body of every command of the engine and the
// battle that the commands read and change.
package handler

type Commands struct {
	session *session
}

func NewCommands() *Commands {
	return &Commands{}
}
