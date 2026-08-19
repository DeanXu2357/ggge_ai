package protocol

type Command struct {
	Name        string `json:"name"`
	Implemented bool   `json:"implemented"`
}

type HelloPayload struct {
	Protocol string    `json:"protocol"`
	Commands []Command `json:"commands"`
}

var Declared = []string{
	"hello",
	"ping",
	"init",
	"deploy_cells",
	"place",
	"roster",
	"reach",
	"actions",
	"reactions",
	"act",
	"rollback",
	"set_unit",
	"advice",
	"certify",
	"export",
	"load",
}

func IsDeclared(name string) bool {
	for _, declared := range Declared {
		if declared == name {
			return true
		}
	}
	return false
}
