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

var wireKinds = map[ActionKind]protocol.ActionKind{
	ActionAttack:      protocol.ActionAttack,
	ActionMapAttack:   protocol.ActionMapAttack,
	ActionReposition:  protocol.ActionReposition,
	ActionStandby:     protocol.ActionStandby,
	ActionSkillRefill: protocol.ActionSkillRefill,
	ActionSkillHeal:   protocol.ActionSkillHeal,
}

var skillSources = map[protocol.SkillSource]SkillSource{
	protocol.SourceCharacter: SourceCharacter,
	protocol.SourceCrew:      SourceCrew,
	protocol.SourceUnit:      SourceUnit,
}

var decodedStances = map[protocol.Stance]Stance{
	protocol.StanceDodge:   StanceDodge,
	protocol.StanceDefend:  StanceDefend,
	protocol.StanceCounter: StanceCounter,
	protocol.StanceNone:    StanceNone,
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

var wireStances = map[Stance]protocol.Stance{
	StanceDodge:   protocol.StanceDodge,
	StanceDefend:  protocol.StanceDefend,
	StanceCounter: protocol.StanceCounter,
	StanceNone:    protocol.StanceNone,
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

// A payload that carries the rules carries every field: a field that the
// payload omits decodes to zero, and no rule value of the mechanism is zero
// (docs/reference/combat-formulas.md).
func DecodeRules(rules *protocol.Rules) (Rules, error) {
	if rules == nil {
		return DefaultRules(), nil
	}
	out := Rules(*rules)
	if err := validateRules(out); err != nil {
		return Rules{}, err
	}
	return out, nil
}

func validateRules(rules Rules) error {
	multipliers := []struct {
		name  string
		value float64
	}{
		{"defend multiplier", rules.DefendMultiplier},
		{"shield multiplier", rules.ShieldMultiplier},
		{"support defense multiplier", rules.SupportDefendMultiplier},
	}
	for _, one := range multipliers {
		if one.value <= 0 || one.value > 1 {
			return fmt.Errorf("the rules carry the %s %v, and a defense multiplier takes the damage down",
				one.name, one.value)
		}
	}
	if rules.DodgeHitPenalty < 0 {
		return fmt.Errorf("the rules carry the dodge penalty %v, and a penalty takes the hit rate down",
			rules.DodgeHitPenalty)
	}
	if rules.Terrain <= 0 {
		return fmt.Errorf("the rules carry the terrain %v, and the terrain divides the damage",
			rules.Terrain)
	}
	if rules.MaxSupportAttackers < 0 {
		return fmt.Errorf("the rules carry the support cap %d, and a cap counts units",
			rules.MaxSupportAttackers)
	}
	if rules.ENRegenFraction < 0 || rules.ENRegenFraction > 1 {
		return fmt.Errorf("the rules carry the energy regeneration %v, and a fraction lies in [0, 1]",
			rules.ENRegenFraction)
	}
	return nil
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
			out.Debuffs = append(out.Debuffs, Debuff(debuff))
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

func EncodeCapabilities(capabilities Capabilities) protocol.ActionsResponse {
	unit := capabilities.Unit
	out := protocol.ActionsResponse{
		Unit:      EncodeUnitStatus(unit),
		MoveCells: EncodeCells(capabilities.MoveCells),
		Weapons:   EncodeWeapons(unit),
		Skills:    EncodeSkills(unit.Skills),
	}
	if unit.Acted {
		out.Error = &protocol.Error{
			Code:    protocol.CodeAlreadyActed,
			Message: fmt.Sprintf("the unit %q acted in this turn", unit.ID),
		}
	}
	return out
}

func EncodeUnitStatus(unit *Unit) protocol.UnitStatus {
	return protocol.UnitStatus{
		UnitID:    unit.ID,
		Faction:   wireFactions[unit.Faction],
		Pos:       EncodeCell(unit.Footprint.Anchor),
		Size:      protocol.Cell{unit.Footprint.Size[0], unit.Footprint.Size[1]},
		HP:        unit.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.EN,
		ENMax:     unit.ENMax,
		MoveRange: unit.MoveRange,
		Acted:     unit.Acted,
	}
}

func EncodeWeapons(unit *Unit) []protocol.WeaponEntry {
	out := make([]protocol.WeaponEntry, 0, len(unit.Weapons))
	for _, weapon := range unit.Weapons {
		entry := protocol.WeaponEntry{
			Name:            weapon.Name,
			RangeMin:        weapon.Range.Min,
			RangeMax:        weapon.Range.Max,
			ENCost:          weapon.ENCost,
			Ammo:            encodeAmmo(unit.Ammo, weapon.Name),
			Accuracy:        weapon.Accuracy,
			CanCounter:      weapon.CanCounter,
			MapWeapon:       weapon.MapWeapon,
			UsableAfterMove: weapon.UsableAfterMove,
			TerrainDamage:   encodeTerrainDamage(weapon.TerrainDamage),
			UnusableIn:      encodeTerrainSet(weapon.UnusableIn),
		}
		out = append(out, entry)
	}
	return out
}

func EncodeSkills(skills []Skill) []protocol.SkillEntry {
	out := make([]protocol.SkillEntry, 0, len(skills))
	for _, skill := range skills {
		out = append(out, protocol.SkillEntry{
			Kind:            wireKinds[skill.Kind],
			Amount:          cloneAmount(skill.Amount),
			Uses:            skill.Uses,
			EndsActivation:  skill.EndsActivation,
			UsableAfterMove: skill.UsableAfterMove,
			RangeMin:        skill.Range.Min,
			RangeMax:        skill.Range.Max,
			Blast:           skill.Blast,
			Affects:         wireAffects[skill.Affects],
		})
	}
	return out
}

func encodeAmmo(ammo map[string]int, name string) *int {
	count, carried := ammo[name]
	if !carried {
		return nil
	}
	return &count
}

func encodeTerrainDamage(scales map[Terrain]float64) map[string]float64 {
	if len(scales) == 0 {
		return nil
	}
	out := make(map[string]float64, len(scales))
	for kind, scale := range scales {
		out[kind.String()] = scale
	}
	return out
}

func encodeTerrainSet(set TerrainSet) []string {
	if len(set) == 0 {
		return nil
	}
	out := make([]string, 0, len(set))
	for kind := TerrainSpace; int(kind) < len(terrainNames); kind++ {
		if set[kind] {
			out = append(out, kind.String())
		}
	}
	return out
}

func DecodeDecision(action *protocol.Decision) (Decision, error) {
	kind, known := actionKinds[action.Kind]
	if !known {
		return Decision{}, fmt.Errorf("the action carries the kind %q, which is not in the contract",
			action.Kind)
	}
	out := Decision{
		UnitID:           action.UnitID,
		Kind:             kind,
		TargetID:         decodeOptionalName(action.TargetID),
		Weapon:           decodeOptionalName(action.Weapon),
		Amount:           cloneAmount(action.Amount),
		SupportDefender:  decodeOptionalName(action.SupportDefender),
		SupportAttackers: append([]string(nil), action.SupportAttackers...),
	}
	if action.Reaction != nil {
		reaction, err := DecodeReaction(*action.Reaction)
		if err != nil {
			return Decision{}, err
		}
		out.Reaction = &reaction
	}
	if action.MoveTo != nil {
		cell := DecodeCell(*action.MoveTo)
		out.MoveTo = &cell
	}
	if action.Aim != nil {
		aim := DecodeCell(*action.Aim)
		out.Aim = &aim
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
		Stance:           stance,
		Weapon:           decodeOptionalName(reaction.Weapon),
		SupportDefender:  decodeOptionalName(reaction.SupportDefender),
		SupportAttackers: append([]string(nil), reaction.SupportAttackers...),
	}, nil
}

func decodeOptionalName(name *string) string {
	if name == nil {
		return ""
	}
	return *name
}

func EncodeEngagement(engagement Engagement) protocol.ReactionsResponse {
	return protocol.ReactionsResponse{
		Defender: protocol.DefenderOptions{
			UnitID:           engagement.Defender.Unit.ID,
			Reactions:        encodeReactionOptions(engagement.Reactions),
			SupportDefenders: encodeSupportDefenders(engagement.Defender.SupportDefenders),
			SupportAttackers: encodeSupportAttackers(engagement.Defender.SupportAttackers),
		},
		Attacker: protocol.AttackerOptions{
			UnitID:           engagement.Attacker.Unit.ID,
			SupportDefenders: encodeSupportDefenders(engagement.Attacker.SupportDefenders),
			SupportAttackers: encodeSupportAttackers(engagement.Attacker.SupportAttackers),
		},
	}
}

func encodeReactionOptions(options []ReactionOption) []protocol.ReactionOption {
	out := make([]protocol.ReactionOption, 0, len(options))
	for _, option := range options {
		entry := protocol.ReactionOption{
			Stance:   wireStances[option.Stance],
			Weapon:   encodeOptionalName(option.Weapon),
			Incoming: EncodeForecast(option.Incoming),
		}
		if option.Counter != nil {
			counter := EncodeForecast(*option.Counter)
			entry.Counter = &counter
		}
		out = append(out, entry)
	}
	return out
}

// The wire carries no integer type, so the damage goes out as a number.
func EncodeForecast(forecast Forecast) protocol.Forecast {
	out := protocol.Forecast{HitRate: forecast.HitRate, Kill: forecast.Kill}
	if forecast.HitRate != nil {
		rate := *forecast.HitRate
		out.HitRate = &rate
	}
	if forecast.Kill != nil {
		kill := *forecast.Kill
		out.Kill = &kill
	}
	if forecast.Damage != nil {
		damage := float64(*forecast.Damage)
		out.Damage = &damage
	}
	return out
}

func encodeSupportDefenders(options []SupportDefendOption) []protocol.SupportDefendOption {
	out := make([]protocol.SupportDefendOption, 0, len(options))
	for _, option := range options {
		out = append(out, protocol.SupportDefendOption{
			UnitID:   option.Unit.ID,
			Incoming: EncodeForecast(option.Incoming),
		})
	}
	return out
}

func encodeSupportAttackers(options []SupportAttackOption) []protocol.SupportAttackOption {
	out := make([]protocol.SupportAttackOption, 0, len(options))
	for _, option := range options {
		out = append(out, protocol.SupportAttackOption{
			UnitID: option.Unit.ID,
			Weapon: option.Weapon.Name,
			Strike: EncodeForecast(option.Strike),
		})
	}
	return out
}

func EncodeUnits(units []Unit) []protocol.Unit {
	out := make([]protocol.Unit, 0, len(units))
	for _, unit := range units {
		out = append(out, EncodeUnit(unit))
	}
	return out
}

// A list and a map hold no null on the wire, so an empty one is an empty
// list and an empty object.
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
		out.Debuffs = append(out.Debuffs, protocol.Debuff(debuff))
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
