package def

type Mech struct {
	HP        int
	EN        int
	Attack    float64
	Defense   float64
	Mobility  float64
	MoveRange int
	Weapons   []Weapon
}

type Pilot struct {
	Ranged   float64
	Melee    float64
	Awaken   float64
	Defense  float64
	Reaction float64
	SP       int
}

type Weapon struct {
	Name            string
	Power           float64
	Range           RadiusRange
	ENCost          int
	Accuracy        float64
	MapWeapon       bool
	UsableAfterMove bool
	DebuffKind      string
	DebuffMagnitude float64
	Categories      []WeaponCategory
}

type RadiusRange struct {
	Min int
	Max int
}

func (r RadiusRange) Holds(distance int) bool {
	return r.Min <= distance && distance <= r.Max
}

type WeaponCategory string

const (
	WeaponCategoryRanged WeaponCategory = "ranged"
	WeaponCategoryMelee  WeaponCategory = "melee"
	WeaponCategoryAwaken WeaponCategory = "awaken"
)

var WeaponCategories = [...]WeaponCategory{
	WeaponCategoryRanged, WeaponCategoryMelee, WeaponCategoryAwaken,
}
