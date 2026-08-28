package handler

type Commands struct {
	session *session
}

func NewCommands() *Commands {
	return &Commands{}
}
