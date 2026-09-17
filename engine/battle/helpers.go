package battle

type Terrain string

const (
	TerrainSpace       Terrain = "space"
	TerrainAtmospheric Terrain = "atmospheric"
	TerrainGround      Terrain = "ground"
	TerrainSurface     Terrain = "surface"
	TerrainUnderwater  Terrain = "underwater"
)

type WeaponCategory string

const (
	WeaponCategoryRanged WeaponCategory = "ranged"
	WeaponCategoryMelee  WeaponCategory = "melee"
	WeaponCategoryAwaken WeaponCategory = "awaken"
)

var WeaponCategories = [...]WeaponCategory{
	WeaponCategoryRanged, WeaponCategoryMelee, WeaponCategoryAwaken,
}

// An empty terrain is the terrain that a state leaves out, and it reads as
// space.
var terrains = map[Terrain]bool{
	"":                 true,
	TerrainSpace:       true,
	TerrainAtmospheric: true,
	TerrainGround:      true,
	TerrainSurface:     true,
	TerrainUnderwater:  true,
}

// WeaponAttribute is the datamine 'weapon_attribute' of a weapon: physical,
// beam or special, and a weapon may carry two. A line of the defender reads
// it ("When the enemy attacks with beam ranged weapons").
type WeaponAttribute string

const (
	WeaponAttributePhysical WeaponAttribute = "physical"
	WeaponAttributeBeam     WeaponAttribute = "beam"
	WeaponAttributeSpecial  WeaponAttribute = "special"
)

var weaponAttributes = map[WeaponAttribute]bool{
	WeaponAttributePhysical: true,
	WeaponAttributeBeam:     true,
	WeaponAttributeSpecial:  true,
}

func (a *WeaponAttribute) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, a, weaponAttributes, "attribute")
}

// MechType is the datamine 'unit_role' of a mech, the '類型' of the game.
type MechType int

const (
	MechTypeAttack  MechType = 1 // 攻擊型
	MechTypeDurable MechType = 2 // 耐久型
	MechTypeSupport MechType = 3 // 支援型
)

// AbilityKind is the effect of a line. The names are the kinds of
// docs/reference/datamine-source.md, from 'trait_type'.
type AbilityKind string

const (
	AbilityAccuracyPercent      AbilityKind = "accuracy_percent"
	AbilityEvasionPercent       AbilityKind = "evasion_percent"
	AbilityMechAttackPercent    AbilityKind = "mech_attack_percent"
	AbilityMechDefensePercent   AbilityKind = "mech_defense_percent"
	AbilityMechMobilityPercent  AbilityKind = "mech_mobility_percent"
	AbilityPilotRangedPercent   AbilityKind = "pilot_ranged_percent"
	AbilityPilotMeleePercent    AbilityKind = "pilot_melee_percent"
	AbilityPilotAwakenPercent   AbilityKind = "pilot_awaken_percent"
	AbilityPilotDefensePercent  AbilityKind = "pilot_defense_percent"
	AbilityPilotReactionPercent AbilityKind = "pilot_reaction_percent"
	AbilityDamageDealtPercent   AbilityKind = "damage_dealt_percent"
	AbilityDamageTakenPercent   AbilityKind = "damage_taken_percent"
	AbilityWeaponENCostPercent  AbilityKind = "weapon_en_cost_percent"
)

// StrikeRole is the condition 'strike_roles' of the datamine: the line holds
// when its holder fires or takes a strike for another unit.
type StrikeRole string

const (
	StrikeRoleSupportAttack  StrikeRole = "support_attack" // support attack and support counter
	StrikeRoleSupportDefense StrikeRole = "support_defense"
)

var weaponCategories = map[WeaponCategory]bool{
	WeaponCategoryRanged: true,
	WeaponCategoryMelee:  true,
	WeaponCategoryAwaken: true,
}

func (t *Terrain) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, t, terrains, "terrain")
}

func (c *WeaponCategory) UnmarshalJSON(data []byte) error {
	return decodeEnum(data, c, weaponCategories, "weapon category")
}

func (c Cell) Before(other Cell) bool {
	if c[0] != other[0] {
		return c[0] < other[0]
	}
	return c[1] < other[1]
}

// Footprint carries no JSON tag: the wire holds the anchor and the size as
// two fields of the unit.
type Footprint struct {
	Anchor Cell
	Size   Cell
}

func (f Footprint) Within(bounds Bounds) bool {
	high := Cell{f.Anchor[0] + f.Size[0] - 1, f.Anchor[1] + f.Size[1] - 1}
	return bounds[0][0] <= f.Anchor[0] && high[0] <= bounds[1][0] &&
		bounds[0][1] <= f.Anchor[1] && high[1] <= bounds[1][1]
}

func (f Footprint) Cells() []Cell {
	out := make([]Cell, 0, f.Size[0]*f.Size[1])
	for dx := 0; dx < f.Size[0]; dx++ {
		for dy := 0; dy < f.Size[1]; dy++ {
			out = append(out, Cell{f.Anchor[0] + dx, f.Anchor[1] + dy})
		}
	}
	return out
}

// A size of zero on an axis is a unit that covers one cell on that axis.
func (u *Unit) Footprint() Footprint {
	out := Footprint{Anchor: u.Pos, Size: u.Size}
	for axis := range out.Size {
		if out.Size[axis] == 0 {
			out.Size[axis] = 1
		}
	}
	return out
}

// PhaseOrder is the rotation of the sides inside one turn.
var PhaseOrder = [...]Faction{FactionAlly, FactionThirdParty, FactionEnemy}

func (f Faction) Opposing() Faction {
	if f == FactionAlly {
		return FactionEnemy
	}
	return FactionAlly
}

func CloneAmount(amount *float64) *float64 {
	if amount == nil {
		return nil
	}
	out := *amount
	return &out
}
