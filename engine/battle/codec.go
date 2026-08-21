package battle

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var factions = map[protocol.Faction]Faction{
	protocol.FactionAlly:       FactionAlly,
	protocol.FactionEnemy:      FactionEnemy,
	protocol.FactionThirdParty: FactionThirdParty,
}

var actionKinds = map[protocol.ActionKind]ActionKind{
	protocol.ActionAttack:      ActionAttack,
	protocol.ActionMapAttack:   ActionMapAttack,
	protocol.ActionReposition:  ActionReposition,
	protocol.ActionStandby:     ActionStandby,
	protocol.ActionSkillRefill: ActionSkillRefill,
	protocol.ActionSkillHeal:   ActionSkillHeal,
}

var skillAffects = map[protocol.SkillAffects]SkillAffects{
	protocol.AffectsAlly:  AffectsAlly,
	protocol.AffectsEnemy: AffectsEnemy,
	protocol.AffectsAll:   AffectsAll,
}

var skillSources = map[protocol.SkillSource]SkillSource{
	protocol.SourceCharacter: SourceCharacter,
	protocol.SourceCrew:      SourceCrew,
	protocol.SourceUnit:      SourceUnit,
}

var decodedStances = map[protocol.Stance]Stance{
	protocol.StanceDodge:   StanceDodge,
	protocol.StanceDefend:  StanceDefend,
	protocol.StanceShield:  StanceShield,
	protocol.StanceCounter: StanceCounter,
}

var wireFactions = map[Faction]protocol.Faction{
	FactionAlly:       protocol.FactionAlly,
	FactionEnemy:      protocol.FactionEnemy,
	FactionThirdParty: protocol.FactionThirdParty,
}

var wireAffects = map[SkillAffects]protocol.SkillAffects{
	AffectsAlly:  protocol.AffectsAlly,
	AffectsEnemy: protocol.AffectsEnemy,
	AffectsAll:   protocol.AffectsAll,
}

var wireSources = map[SkillSource]protocol.SkillSource{
	SourceCharacter: protocol.SourceCharacter,
	SourceCrew:      protocol.SourceCrew,
	SourceUnit:      protocol.SourceUnit,
}

var wireKinds = map[ActionKind]protocol.ActionKind{
	ActionAttack:      protocol.ActionAttack,
	ActionMapAttack:   protocol.ActionMapAttack,
	ActionReposition:  protocol.ActionReposition,
	ActionStandby:     protocol.ActionStandby,
	ActionSkillRefill: protocol.ActionSkillRefill,
	ActionSkillHeal:   protocol.ActionSkillHeal,
}

var wireStances = map[Stance]protocol.Stance{
	StanceDodge:   protocol.StanceDodge,
	StanceDefend:  protocol.StanceDefend,
	StanceShield:  protocol.StanceShield,
	StanceCounter: protocol.StanceCounter,
}

func DecodeState(state *protocol.BattleState) (*Board, error) {
	if state == nil {
		return nil, fmt.Errorf("the payload carries no state")
	}
	bounds, err := decodeBounds(state.Bounds)
	if err != nil {
		return nil, err
	}
	units, err := decodeUnits(state.Units)
	if err != nil {
		return nil, err
	}
	board, err := NewBoard(bounds, units, DefaultRules())
	if err != nil {
		return nil, err
	}
	if board.DefaultTerrain, err = decodeTerrain(state.Terrain); err != nil {
		return nil, err
	}
	if board.TerrainCells, err = decodeTerrainCells(state.TerrainCells); err != nil {
		return nil, err
	}
	phase, known := factions[state.Phase]
	if !known {
		return nil, fmt.Errorf("the state carries the phase %q, which is not in the contract",
			state.Phase)
	}
	board.Phase = phase
	board.Turn = state.Turn
	return board, nil
}

func decodeTerrain(name string) (Terrain, error) {
	if name == "" {
		return TerrainSpace, nil
	}
	return ParseTerrain(name)
}

func decodeTerrainCells(cells []protocol.TerrainCell) (map[Cell]Terrain, error) {
	if len(cells) == 0 {
		return nil, nil
	}
	out := make(map[Cell]Terrain, len(cells))
	for _, entry := range cells {
		kind, err := ParseTerrain(entry.Terrain)
		if err != nil {
			return nil, fmt.Errorf("the cell %v carries a terrain outside the contract: %w",
				entry.Cell, err)
		}
		out[DecodeCell(entry.Cell)] = kind
	}
	return out, nil
}

// DecodeRules reads the rule overrides of a stage. A payload with no value
// gives the defaults. The terrain divides the combat base damage, so a terrain
// of zero or less is no rule set (docs/reference/combat-formulas.md).
func DecodeRules(rules *protocol.Rules) (Rules, error) {
	if rules == nil {
		return DefaultRules(), nil
	}
	if rules.Terrain <= 0 {
		return Rules{}, fmt.Errorf("the rules carry the terrain %v, and the terrain divides the damage",
			rules.Terrain)
	}
	return Rules{
		DefendMultiplier:        rules.DefendMultiplier,
		ShieldMultiplier:        rules.ShieldMultiplier,
		SupportDefendMultiplier: rules.SupportDefendMultiplier,
		DodgeHitPenalty:         rules.DodgeHitPenalty,
		Terrain:                 rules.Terrain,
		MaxSupportAttackers:     rules.MaxSupportAttackers,
		ENRegenFraction:         rules.ENRegenFraction,
	}, nil
}

func decodeUnits(units []protocol.Unit) ([]Unit, error) {
	if units == nil {
		return nil, nil
	}
	out := make([]Unit, 0, len(units))
	for index := range units {
		unit, err := decodeUnit(&units[index])
		if err != nil {
			return nil, err
		}
		out = append(out, unit)
	}
	return out, nil
}

func DecodeCell(cell protocol.Cell) Cell {
	return Cell{cell[0], cell[1]}
}

func EncodeCell(cell Cell) protocol.Cell {
	return protocol.Cell{cell[0], cell[1]}
}

func EncodeCells(cells []Cell) []protocol.Cell {
	out := make([]protocol.Cell, 0, len(cells))
	for _, cell := range cells {
		out = append(out, EncodeCell(cell))
	}
	return out
}

func decodeUnit(unit *protocol.Unit) (Unit, error) {
	faction, known := factions[unit.Faction]
	if !known {
		return Unit{}, fmt.Errorf("unit %q carries the faction %q, which is not in the contract",
			unit.UnitID, unit.Faction)
	}
	footprint, err := decodeFootprint(unit)
	if err != nil {
		return Unit{}, err
	}
	out := Unit{
		ID:        unit.UnitID,
		Faction:   faction,
		Footprint: footprint,
		HP:        unit.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.EN,
		ENMax:     unit.ENMax,
		Pilot: Pilot{
			Attack:   unit.PilotAttack,
			Defense:  unit.PilotDefense,
			Reaction: unit.Reaction,
		},
		Mech: Mech{
			Attack:    unit.UnitAttack,
			Defense:   unit.UnitDefense,
			Mobility:  unit.Mobility,
			HP:        unit.MechHP,
			EN:        unit.MechEN,
			MoveRange: unit.MechMoveRange,
		},
		MoveRange:               unit.MoveRange,
		Acted:                   unit.Acted,
		ChanceSteps:             unit.ChanceSteps,
		ChanceStepsMax:          unit.ChanceStepsMax,
		SupportDefendCharges:    unit.SupportDefendCharges,
		SupportDefendChargesMax: unit.SupportDefendChargesMax,
		SupportAttackCharges:    unit.SupportAttackCharges,
		SupportAttackChargesMax: unit.SupportAttackChargesMax,
		HasShield:               unit.HasShield,
		AttackShield:            unit.AttackShield,
		InterceptionReduction:   unit.InterceptionReduction,
	}
	if out.Weapons, err = decodeWeapons(unit.UnitID, unit.Weapons); err != nil {
		return Unit{}, err
	}
	if out.Mech.Weapons, err = decodeWeapons(unit.UnitID, unit.MechWeapons); err != nil {
		return Unit{}, err
	}
	if unit.Skills != nil {
		out.Skills = make([]Skill, 0, len(unit.Skills))
		for _, skill := range unit.Skills {
			decoded, err := decodeSkill(unit.UnitID, skill)
			if err != nil {
				return Unit{}, err
			}
			out.Skills = append(out.Skills, decoded)
		}
	}
	if unit.Ammo != nil {
		out.Ammo = make(map[string]int, len(unit.Ammo))
		for name, count := range unit.Ammo {
			out.Ammo[name] = count
		}
	}
	if unit.Debuffs != nil {
		out.Debuffs = make([]Debuff, 0, len(unit.Debuffs))
		for _, debuff := range unit.Debuffs {
			out.Debuffs = append(out.Debuffs, Debuff{
				Kind:         debuff.Kind,
				Magnitude:    debuff.Magnitude,
				AppliedPhase: debuff.AppliedPhase,
			})
		}
	}
	return out, nil
}

func decodeWeapons(unitID string, weapons []protocol.Weapon) ([]Weapon, error) {
	if weapons == nil {
		return nil, nil
	}
	out := make([]Weapon, 0, len(weapons))
	for index := range weapons {
		weapon, err := decodeWeapon(&weapons[index])
		if err != nil {
			return nil, fmt.Errorf("unit %q: %w", unitID, err)
		}
		out = append(out, weapon)
	}
	return out, nil
}

func decodeWeapon(weapon *protocol.Weapon) (Weapon, error) {
	out := Weapon{
		Name:            weapon.Name,
		Power:           weapon.Power,
		Range:           RadiusRange{Min: weapon.RangeMin, Max: weapon.RangeMax},
		ENCost:          weapon.ENCost,
		Accuracy:        weapon.Accuracy,
		CanCounter:      weapon.CanCounter,
		MapWeapon:       weapon.MapWeapon,
		UsableAfterMove: weapon.UsableAfterMove,
		Blast:           weapon.Blast,
		DebuffMagnitude: weapon.DebuffMagnitude,
	}
	if weapon.DebuffKind != nil {
		out.DebuffKind = *weapon.DebuffKind
	}
	for name, scale := range weapon.TerrainDamage {
		kind, err := ParseTerrain(name)
		if err != nil {
			return Weapon{}, fmt.Errorf("weapon %q: %w", weapon.Name, err)
		}
		if out.TerrainDamage == nil {
			out.TerrainDamage = make(map[Terrain]float64, len(weapon.TerrainDamage))
		}
		out.TerrainDamage[kind] = scale
	}
	for _, name := range weapon.UnusableIn {
		kind, err := ParseTerrain(name)
		if err != nil {
			return Weapon{}, fmt.Errorf("weapon %q: %w", weapon.Name, err)
		}
		if out.UnusableIn == nil {
			out.UnusableIn = make(TerrainSet, len(weapon.UnusableIn))
		}
		out.UnusableIn[kind] = true
	}
	return out, nil
}

func decodeSkill(unitID string, skill protocol.Skill) (Skill, error) {
	kind, known := actionKinds[skill.Kind]
	if !known {
		return Skill{}, fmt.Errorf("unit %q carries a skill of the kind %q, which is not in the contract",
			unitID, skill.Kind)
	}
	source, known := skillSources[skill.Source]
	if !known {
		return Skill{}, fmt.Errorf("unit %q carries a skill of the source %q, which is not in the contract",
			unitID, skill.Source)
	}
	affects, known := skillAffects[skill.Affects]
	if !known {
		return Skill{}, fmt.Errorf("unit %q carries a skill that affects %q, which is not in the contract",
			unitID, skill.Affects)
	}
	return Skill{
		Kind:            kind,
		Source:          source,
		Amount:          cloneAmount(skill.Amount),
		Uses:            skill.Uses,
		EndsActivation:  skill.EndsActivation,
		UsableAfterMove: skill.UsableAfterMove,
		Range:           RadiusRange{Min: skill.RangeMin, Max: skill.RangeMax},
		Blast:           skill.Blast,
		Affects:         affects,
	}, nil
}

func EncodeDecisions(decisions []Decision) []protocol.Decision {
	out := make([]protocol.Decision, 0, len(decisions))
	for _, decision := range decisions {
		out = append(out, EncodeDecision(decision))
	}
	return out
}

// EncodeDecision writes every field of the wire type. An enumerated action
// settles no die, so 'hit', 'counter_hit' and 'support_hit' stay null.
func EncodeDecision(decision Decision) protocol.Decision {
	out := protocol.Decision{
		UnitID:   decision.UnitID,
		Kind:     wireKinds[decision.Kind],
		MoveTo:   encodeOptionalCell(decision.MoveTo),
		TargetID: encodeOptionalName(decision.TargetID),
		Weapon:   encodeOptionalName(decision.Weapon),
		Amount:   cloneAmount(decision.Amount),
		Support:  decision.Support,
		Aim:      encodeOptionalCell(decision.Aim),
	}
	if decision.Reaction != nil {
		reaction := EncodeReaction(*decision.Reaction)
		out.Reaction = &reaction
	}
	return out
}

// DecodeDecision reads one activation. The three die fields of the wire
// decision belong to the dice of the resolution, not to the decision.
func DecodeDecision(decision protocol.Decision) (Decision, error) {
	kind, known := actionKinds[decision.Kind]
	if !known {
		return Decision{}, fmt.Errorf("the action carries the kind %q, which is not in the contract",
			decision.Kind)
	}
	out := Decision{
		UnitID:   decision.UnitID,
		Kind:     kind,
		TargetID: name(decision.TargetID),
		Weapon:   name(decision.Weapon),
		Amount:   cloneAmount(decision.Amount),
		Support:  decision.Support,
	}
	if decision.MoveTo != nil {
		cell := DecodeCell(*decision.MoveTo)
		out.MoveTo = &cell
	}
	if decision.Aim != nil {
		cell := DecodeCell(*decision.Aim)
		out.Aim = &cell
	}
	if decision.Reaction != nil {
		reaction, err := DecodeReaction(*decision.Reaction)
		if err != nil {
			return Decision{}, err
		}
		out.Reaction = &reaction
	}
	return out, nil
}

func DecodeReaction(reaction protocol.Reaction) (Reaction, error) {
	stance, known := decodedStances[reaction.Stance]
	if !known {
		return Reaction{}, fmt.Errorf("the reaction carries the stance %q, which is not in the contract",
			reaction.Stance)
	}
	return Reaction{
		Stance:        stance,
		Weapon:        name(reaction.Weapon),
		SupportDefend: reaction.SupportDefend,
		SupportAttack: reaction.SupportAttack,
	}, nil
}

func name(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func EncodeReactions(reactions []Reaction) []protocol.Reaction {
	out := make([]protocol.Reaction, 0, len(reactions))
	for _, reaction := range reactions {
		out = append(out, EncodeReaction(reaction))
	}
	return out
}

func EncodeReaction(reaction Reaction) protocol.Reaction {
	return protocol.Reaction{
		Stance:        wireStances[reaction.Stance],
		Weapon:        encodeOptionalName(reaction.Weapon),
		SupportDefend: reaction.SupportDefend,
		SupportAttack: reaction.SupportAttack,
	}
}

func EncodeUnits(units []Unit) []protocol.Unit {
	out := make([]protocol.Unit, 0, len(units))
	for _, unit := range units {
		out = append(out, EncodeUnit(unit))
	}
	return out
}

// EncodeUnit writes every field of the wire type. A list and a map hold no
// null on the wire, so an empty one is an empty list and an empty object.
func EncodeUnit(unit Unit) protocol.Unit {
	out := protocol.Unit{
		UnitID:                  unit.ID,
		Faction:                 wireFactions[unit.Faction],
		Pos:                     EncodeCell(unit.Footprint.Anchor),
		Size:                    protocol.Cell{unit.Footprint.Size[0], unit.Footprint.Size[1]},
		HP:                      unit.HP,
		MaxHP:                   unit.MaxHP,
		EN:                      unit.EN,
		ENMax:                   unit.ENMax,
		UnitAttack:              unit.Mech.Attack,
		UnitDefense:             unit.Mech.Defense,
		PilotAttack:             unit.Pilot.Attack,
		PilotDefense:            unit.Pilot.Defense,
		Reaction:                unit.Pilot.Reaction,
		Mobility:                unit.Mech.Mobility,
		MoveRange:               unit.MoveRange,
		MechHP:                  unit.Mech.HP,
		MechEN:                  unit.Mech.EN,
		MechMoveRange:           unit.Mech.MoveRange,
		Weapons:                 make([]protocol.Weapon, 0, len(unit.Weapons)),
		Skills:                  make([]protocol.Skill, 0, len(unit.Skills)),
		Acted:                   unit.Acted,
		ChanceSteps:             unit.ChanceSteps,
		ChanceStepsMax:          unit.ChanceStepsMax,
		SupportDefendCharges:    unit.SupportDefendCharges,
		SupportDefendChargesMax: unit.SupportDefendChargesMax,
		SupportAttackCharges:    unit.SupportAttackCharges,
		SupportAttackChargesMax: unit.SupportAttackChargesMax,
		HasShield:               unit.HasShield,
		AttackShield:            unit.AttackShield,
		InterceptionReduction:   unit.InterceptionReduction,
		Ammo:                    make(map[string]int, len(unit.Ammo)),
		Debuffs:                 make([]protocol.Debuff, 0, len(unit.Debuffs)),
	}
	for _, weapon := range unit.Weapons {
		out.Weapons = append(out.Weapons, encodeWeapon(weapon))
	}
	// The base weapons of the mech are 'omitempty' on the wire, so an absent
	// list stays absent and the round trip gives the same bytes.
	if len(unit.Mech.Weapons) > 0 {
		out.MechWeapons = make([]protocol.Weapon, 0, len(unit.Mech.Weapons))
		for _, weapon := range unit.Mech.Weapons {
			out.MechWeapons = append(out.MechWeapons, encodeWeapon(weapon))
		}
	}
	for _, skill := range unit.Skills {
		out.Skills = append(out.Skills, encodeSkill(skill))
	}
	for weapon, count := range unit.Ammo {
		out.Ammo[weapon] = count
	}
	for _, debuff := range unit.Debuffs {
		out.Debuffs = append(out.Debuffs, protocol.Debuff{
			Kind:         debuff.Kind,
			Magnitude:    debuff.Magnitude,
			AppliedPhase: debuff.AppliedPhase,
		})
	}
	return out
}

func encodeWeapon(weapon Weapon) protocol.Weapon {
	out := protocol.Weapon{
		Name:            weapon.Name,
		Power:           weapon.Power,
		RangeMin:        weapon.Range.Min,
		RangeMax:        weapon.Range.Max,
		ENCost:          weapon.ENCost,
		Accuracy:        weapon.Accuracy,
		CanCounter:      weapon.CanCounter,
		MapWeapon:       weapon.MapWeapon,
		UsableAfterMove: weapon.UsableAfterMove,
		Blast:           weapon.Blast,
		DebuffMagnitude: weapon.DebuffMagnitude,
	}
	if weapon.DebuffKind != "" {
		kind := weapon.DebuffKind
		out.DebuffKind = &kind
	}
	for kind, scale := range weapon.TerrainDamage {
		if out.TerrainDamage == nil {
			out.TerrainDamage = make(map[string]float64, len(weapon.TerrainDamage))
		}
		out.TerrainDamage[kind.String()] = scale
	}
	// The wire form must not change between two encodes of one weapon, and a
	// map has no order, so the terrain names come out in the order of the enum.
	for kind := range Terrain(len(terrainNames)) {
		if weapon.UnusableIn[kind] {
			out.UnusableIn = append(out.UnusableIn, kind.String())
		}
	}
	return out
}

func encodeSkill(skill Skill) protocol.Skill {
	return protocol.Skill{
		Kind:            wireKinds[skill.Kind],
		Source:          wireSources[skill.Source],
		Amount:          cloneAmount(skill.Amount),
		Uses:            skill.Uses,
		EndsActivation:  skill.EndsActivation,
		UsableAfterMove: skill.UsableAfterMove,
		RangeMin:        skill.Range.Min,
		RangeMax:        skill.Range.Max,
		Blast:           skill.Blast,
		Affects:         wireAffects[skill.Affects],
	}
}

func encodeOptionalCell(cell *Cell) *protocol.Cell {
	if cell == nil {
		return nil
	}
	out := EncodeCell(*cell)
	return &out
}

func encodeOptionalName(name string) *string {
	if name == "" {
		return nil
	}
	return &name
}

func decodeFootprint(unit *protocol.Unit) (Footprint, error) {
	size := Size{unit.Size[0], unit.Size[1]}
	for axis := range size {
		if size[axis] < 0 {
			return Footprint{}, fmt.Errorf("unit %q carries the size %v", unit.UnitID, unit.Size)
		}
		if size[axis] == 0 {
			size[axis] = 1
		}
	}
	return Footprint{Anchor: DecodeCell(unit.Pos), Size: size}, nil
}

func decodeBounds(bounds *protocol.Bounds) (Bounds, error) {
	if bounds == nil {
		return Bounds{}, fmt.Errorf("the state carries no bounds")
	}
	return Bounds{Low: DecodeCell(bounds[0]), High: DecodeCell(bounds[1])}, nil
}
