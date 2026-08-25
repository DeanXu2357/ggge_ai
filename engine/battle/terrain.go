package battle

import "fmt"

type Terrain int

const (
	TerrainSpace Terrain = iota
	TerrainAtmospheric
	TerrainGround
	TerrainSurface
	TerrainUnderwater
)

var terrainNames = [...]string{
	TerrainSpace:       "space",
	TerrainAtmospheric: "atmospheric",
	TerrainGround:      "ground",
	TerrainSurface:     "surface",
	TerrainUnderwater:  "underwater",
}

func (t Terrain) String() string {
	if t < 0 || int(t) >= len(terrainNames) {
		return fmt.Sprintf("terrain(%d)", int(t))
	}
	return terrainNames[t]
}

func ParseTerrain(name string) (Terrain, error) {
	for kind, known := range terrainNames {
		if known == name {
			return Terrain(kind), nil
		}
	}
	return 0, fmt.Errorf("the terrain %q is not in the contract", name)
}
