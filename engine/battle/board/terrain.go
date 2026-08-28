package board

import "fmt"

type terrain int

const (
	terrainSpace terrain = iota
	terrainAtmospheric
	terrainGround
	terrainSurface
	terrainUnderwater
)

var terrainNames = [...]string{
	terrainSpace:       "space",
	terrainAtmospheric: "atmospheric",
	terrainGround:      "ground",
	terrainSurface:     "surface",
	terrainUnderwater:  "underwater",
}

func (t terrain) String() string {
	if t < 0 || int(t) >= len(terrainNames) {
		return fmt.Sprintf("terrain(%d)", int(t))
	}
	return terrainNames[t]
}

func parseTerrain(name string) (terrain, error) {
	for kind, known := range terrainNames {
		if known == name {
			return terrain(kind), nil
		}
	}
	return 0, fmt.Errorf("the terrain %q is not in the contract", name)
}
