package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var factions = map[protocol.Faction]battle.Faction{
	protocol.FactionAlly:       battle.FactionAlly,
	protocol.FactionEnemy:      battle.FactionEnemy,
	protocol.FactionThirdParty: battle.FactionThirdParty,
}

var actionKinds = map[protocol.ActionKind]battle.ActionKind{
	protocol.ActionAttack:     battle.ActionAttack,
	protocol.ActionMapAttack:  battle.ActionMapAttack,
	protocol.ActionReposition: battle.ActionReposition,
	protocol.ActionStandby:    battle.ActionStandby,
}

var skillAffects = map[protocol.SkillAffects]battle.SkillAffects{
	protocol.AffectsAlly:  battle.AffectsAlly,
	protocol.AffectsEnemy: battle.AffectsEnemy,
	protocol.AffectsAll:   battle.AffectsAll,
}

var wireKinds = map[battle.ActionKind]protocol.ActionKind{
	battle.ActionAttack:     protocol.ActionAttack,
	battle.ActionMapAttack:  protocol.ActionMapAttack,
	battle.ActionReposition: protocol.ActionReposition,
	battle.ActionStandby:    protocol.ActionStandby,
}

var skillSources = map[protocol.SkillSource]battle.SkillSource{
	protocol.SourcePilot: battle.SourcePilot,
	protocol.SourceCrew:  battle.SourceCrew,
	protocol.SourceMech:  battle.SourceMech,
}

var decodedStances = map[protocol.Stance]battle.Stance{
	protocol.StanceDodge:   battle.StanceDodge,
	protocol.StanceDefend:  battle.StanceDefend,
	protocol.StanceCounter: battle.StanceCounter,
	protocol.StanceNone:    battle.StanceNone,
}

var wireFactions = map[battle.Faction]protocol.Faction{
	battle.FactionAlly:       protocol.FactionAlly,
	battle.FactionEnemy:      protocol.FactionEnemy,
	battle.FactionThirdParty: protocol.FactionThirdParty,
}

var wireAffects = map[battle.SkillAffects]protocol.SkillAffects{
	battle.AffectsAlly:  protocol.AffectsAlly,
	battle.AffectsEnemy: protocol.AffectsEnemy,
	battle.AffectsAll:   protocol.AffectsAll,
}

var wireSources = map[battle.SkillSource]protocol.SkillSource{
	battle.SourcePilot: protocol.SourcePilot,
	battle.SourceCrew:  protocol.SourceCrew,
	battle.SourceMech:  protocol.SourceMech,
}

var wireStances = map[battle.Stance]protocol.Stance{
	battle.StanceDodge:   protocol.StanceDodge,
	battle.StanceDefend:  protocol.StanceDefend,
	battle.StanceCounter: protocol.StanceCounter,
	battle.StanceNone:    protocol.StanceNone,
}

func cloneAmount(amount *float64) *float64 {
	if amount == nil {
		return nil
	}
	out := *amount
	return &out
}

func EncodeFaction(faction battle.Faction) protocol.Faction {
	return wireFactions[faction]
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
	b, err := New(bounds, units)
	if err != nil {
		return nil, err
	}
	if b.defaultTerrain, err = decodeTerrain(state.Terrain); err != nil {
		return nil, err
	}
	if b.terrainCells, err = decodeTerrainCells(state.TerrainCells); err != nil {
		return nil, err
	}
	phase, known := factions[state.Phase]
	if !known {
		return nil, fmt.Errorf("the state carries the phase %q, which is not in the contract",
			state.Phase)
	}
	b.phase = phase
	b.turn = state.Turn
	return b, nil
}

func decodeTerrain(name string) (battle.Terrain, error) {
	if name == "" {
		return battle.TerrainSpace, nil
	}
	return battle.ParseTerrain(name)
}

func decodeTerrainCells(cells []protocol.TerrainCell) (map[battle.Cell]battle.Terrain, error) {
	if len(cells) == 0 {
		return nil, nil
	}
	out := make(map[battle.Cell]battle.Terrain, len(cells))
	for _, entry := range cells {
		kind, err := battle.ParseTerrain(entry.Terrain)
		if err != nil {
			return nil, fmt.Errorf("the cell %v carries a terrain outside the contract: %w",
				entry.Cell, err)
		}
		out[DecodeCell(entry.Cell)] = kind
	}
	return out, nil
}

func decodeUnits(units []protocol.Unit) ([]battle.Unit, error) {
	if units == nil {
		return nil, nil
	}
	out := make([]battle.Unit, 0, len(units))
	for index := range units {
		unit, err := decodeUnit(&units[index])
		if err != nil {
			return nil, err
		}
		out = append(out, unit)
	}
	return out, nil
}

func DecodeCell(cell protocol.Cell) battle.Cell {
	return battle.Cell{cell[0], cell[1]}
}

func EncodeCell(cell battle.Cell) protocol.Cell {
	return protocol.Cell{cell[0], cell[1]}
}

func EncodeCells(cells []battle.Cell) []protocol.Cell {
	out := make([]protocol.Cell, 0, len(cells))
	for _, cell := range cells {
		out = append(out, EncodeCell(cell))
	}
	return out
}

func decodeUnit(unit *protocol.Unit) (battle.Unit, error) {
	faction, known := factions[unit.Faction]
	if !known {
		return battle.Unit{}, fmt.Errorf("unit %q carries the faction %q, which is not in the contract",
			unit.UnitID, unit.Faction)
	}
	footprint, err := decodeFootprint(unit)
	if err != nil {
		return battle.Unit{}, err
	}
	out := battle.Unit{
		ID:        unit.UnitID,
		Faction:   faction,
		Footprint: footprint,
		HP:        unit.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.EN,
		ENMax:     unit.ENMax,
		SP:        unit.SP,
		SPMax:     unit.SPMax,
		Pilot: battle.Pilot{
			Ranged:   unit.Pilot.Ranged,
			Melee:    unit.Pilot.Melee,
			Awaken:   unit.Pilot.Awaken,
			Defense:  unit.Pilot.Defense,
			Reaction: unit.Pilot.Reaction,
			SP:       unit.Pilot.SP,
		},
		Mech: battle.Mech{
			HP:        unit.Mech.HP,
			EN:        unit.Mech.EN,
			Attack:    unit.Mech.Attack,
			Defense:   unit.Mech.Defense,
			Mobility:  unit.Mech.Mobility,
			MoveRange: unit.Mech.MoveRange,
		},
		Acted:                   unit.Acted,
		ChanceSteps:             unit.ChanceSteps,
		ChanceStepsMax:          unit.ChanceStepsMax,
		SupportDefendCharges:    unit.SupportDefendCharges,
		SupportDefendChargesMax: unit.SupportDefendChargesMax,
		SupportAttackCharges:    unit.SupportAttackCharges,
		SupportAttackChargesMax: unit.SupportAttackChargesMax,
		HasShield:               unit.HasShield,
		SupportDefendWhenAttack: unit.SupportDefendWhenAttack,
	}
	if out.Mech.Weapons, err = decodeWeapons(unit.UnitID, unit.Mech.Weapons); err != nil {
		return battle.Unit{}, err
	}
	if unit.Skills != nil {
		out.Skills = make([]battle.Skill, 0, len(unit.Skills))
		for _, skill := range unit.Skills {
			decoded, err := decodeSkill(unit.UnitID, skill)
			if err != nil {
				return battle.Unit{}, err
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
		out.Debuffs = make([]battle.Debuff, 0, len(unit.Debuffs))
		for _, debuff := range unit.Debuffs {
			out.Debuffs = append(out.Debuffs, battle.Debuff(debuff))
		}
	}
	return out, nil
}

func decodeWeapons(unitID string, weapons []protocol.Weapon) ([]battle.Weapon, error) {
	if weapons == nil {
		return nil, nil
	}
	out := make([]battle.Weapon, 0, len(weapons))
	for index := range weapons {
		weapon, err := decodeWeapon(&weapons[index])
		if err != nil {
			return nil, fmt.Errorf("unit %q: %w", unitID, err)
		}
		out = append(out, weapon)
	}
	return out, nil
}

func decodeWeapon(weapon *protocol.Weapon) (battle.Weapon, error) {
	out := battle.Weapon{
		Name:            weapon.Name,
		Power:           weapon.Power,
		Range:           battle.RadiusRange{Min: weapon.RangeMin, Max: weapon.RangeMax},
		ENCost:          weapon.ENCost,
		Accuracy:        weapon.Accuracy,
		CanCounter:      weapon.CanCounter,
		MapWeapon:       weapon.MapWeapon,
		UsableAfterMove: weapon.UsableAfterMove,
		DebuffMagnitude: weapon.DebuffMagnitude,
	}
	if weapon.DebuffKind != nil {
		out.DebuffKind = *weapon.DebuffKind
	}
	for _, name := range weapon.Categories {
		category, err := battle.ParseWeaponCategory(name)
		if err != nil {
			return battle.Weapon{}, fmt.Errorf("the weapon %q carries %w", weapon.Name, err)
		}
		out.Categories = append(out.Categories, category)
	}
	return out, nil
}

func decodeSkill(unitID string, skill protocol.Skill) (battle.Skill, error) {
	source, known := skillSources[skill.Source]
	if !known {
		return battle.Skill{}, fmt.Errorf("unit %q carries a skill of the source %q, which is not in the contract",
			unitID, skill.Source)
	}
	affects, known := skillAffects[skill.Affects]
	if !known {
		return battle.Skill{}, fmt.Errorf("unit %q carries a skill that affects %q, which is not in the contract",
			unitID, skill.Affects)
	}
	return battle.Skill{
		Kind:            battle.SkillKind(skill.Kind),
		Source:          source,
		Amount:          cloneAmount(skill.Amount),
		Uses:            skill.Uses,
		EndsActivation:  skill.EndsActivation,
		UsableAfterMove: skill.UsableAfterMove,
		Range:           battle.RadiusRange{Min: skill.RangeMin, Max: skill.RangeMax},
		Blast:           skill.Blast,
		Affects:         affects,
	}, nil
}

func EncodeCapabilities(capabilities battle.Capabilities) protocol.ActionsResponse {
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

func EncodeUnitStatus(unit *battle.Unit) protocol.UnitStatus {
	return protocol.UnitStatus{
		UnitID:    unit.ID,
		Faction:   wireFactions[unit.Faction],
		Pos:       EncodeCell(unit.Footprint.Anchor),
		Size:      protocol.Cell{unit.Footprint.Size[0], unit.Footprint.Size[1]},
		HP:        unit.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.EN,
		ENMax:     unit.ENMax,
		MoveRange: unit.Mech.MoveRange,
		Acted:     unit.Acted,
	}
}

func EncodeWeapons(unit *battle.Unit) []protocol.WeaponEntry {
	out := make([]protocol.WeaponEntry, 0, len(unit.Mech.Weapons))
	for _, weapon := range unit.Mech.Weapons {
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
		}
		out = append(out, entry)
	}
	return out
}

func EncodeSkills(skills []battle.Skill) []protocol.SkillEntry {
	out := make([]protocol.SkillEntry, 0, len(skills))
	for _, skill := range skills {
		out = append(out, protocol.SkillEntry{
			Kind:            protocol.SkillKind(skill.Kind),
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

func DecodeDecision(action *protocol.Decision) (battle.Decision, error) {
	kind, known := actionKinds[action.Kind]
	if !known {
		return battle.Decision{}, fmt.Errorf("the action carries the kind %q, which is not in the contract",
			action.Kind)
	}
	out := battle.Decision{
		UnitID:           action.UnitID,
		Kind:             kind,
		TargetID:         decodeOptionalName(action.TargetID),
		Weapon:           decodeOptionalName(action.Weapon),
		Amount:           cloneAmount(action.Amount),
		SupportDefender:  decodeOptionalName(action.SupportDefender),
		SupportAttackers: append([]string(nil), action.SupportAttackers...),
	}
	if action.ResponseAttack != nil {
		responseAttack, err := DecodeResponseAttack(*action.ResponseAttack)
		if err != nil {
			return battle.Decision{}, err
		}
		out.ResponseAttack = &responseAttack
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

func DecodeResponseAttack(responseAttack protocol.ResponseAttack) (battle.ResponseAttack, error) {
	stance, known := decodedStances[responseAttack.Stance]
	if !known {
		return battle.ResponseAttack{}, fmt.Errorf("the response attack carries the stance %q, which is not in the contract",
			responseAttack.Stance)
	}
	return battle.ResponseAttack{
		Stance:           stance,
		Weapon:           decodeOptionalName(responseAttack.Weapon),
		SupportDefender:  decodeOptionalName(responseAttack.SupportDefender),
		SupportAttackers: append([]string(nil), responseAttack.SupportAttackers...),
	}, nil
}

func decodeOptionalName(name *string) string {
	if name == nil {
		return ""
	}
	return *name
}

func EncodeEngagement(engagement battle.Engagement) protocol.ResponseAttacksResponse {
	return protocol.ResponseAttacksResponse{
		Defender: protocol.DefenderOptions{
			UnitID:           engagement.Defender.Unit.ID,
			ResponseAttacks:  encodeResponseAttackOptions(engagement.ResponseAttacks),
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

func encodeResponseAttackOptions(options []battle.ResponseAttackOption) []protocol.ResponseAttackOption {
	out := make([]protocol.ResponseAttackOption, 0, len(options))
	for _, option := range options {
		entry := protocol.ResponseAttackOption{
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
func EncodeForecast(forecast battle.Forecast) protocol.Forecast {
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

func encodeSupportDefenders(options []battle.SupportDefendOption) []protocol.SupportDefendOption {
	out := make([]protocol.SupportDefendOption, 0, len(options))
	for _, option := range options {
		out = append(out, protocol.SupportDefendOption{
			UnitID:   option.Unit.ID,
			Incoming: EncodeForecast(option.Incoming),
		})
	}
	return out
}

func encodeSupportAttackers(options []battle.SupportAttackOption) []protocol.SupportAttackOption {
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

func EncodeUnits(units []battle.Unit) []protocol.Unit {
	out := make([]protocol.Unit, 0, len(units))
	for _, unit := range units {
		out = append(out, EncodeUnit(unit))
	}
	return out
}

// A list and a map hold no null on the wire, so an empty one is an empty
// list and an empty object.
func EncodeUnit(unit battle.Unit) protocol.Unit {
	out := protocol.Unit{
		UnitID:  unit.ID,
		Faction: wireFactions[unit.Faction],
		Pos:     EncodeCell(unit.Footprint.Anchor),
		Size:    protocol.Cell{unit.Footprint.Size[0], unit.Footprint.Size[1]},
		HP:      unit.HP,
		MaxHP:   unit.MaxHP,
		EN:      unit.EN,
		ENMax:   unit.ENMax,
		SP:      unit.SP,
		SPMax:   unit.SPMax,
		Pilot: protocol.Pilot{
			Ranged:   unit.Pilot.Ranged,
			Melee:    unit.Pilot.Melee,
			Awaken:   unit.Pilot.Awaken,
			Defense:  unit.Pilot.Defense,
			Reaction: unit.Pilot.Reaction,
			SP:       unit.Pilot.SP,
		},
		Mech: protocol.Mech{
			HP:        unit.Mech.HP,
			EN:        unit.Mech.EN,
			Attack:    unit.Mech.Attack,
			Defense:   unit.Mech.Defense,
			Mobility:  unit.Mech.Mobility,
			MoveRange: unit.Mech.MoveRange,
			Weapons:   make([]protocol.Weapon, 0, len(unit.Mech.Weapons)),
		},
		Skills:                  make([]protocol.Skill, 0, len(unit.Skills)),
		Acted:                   unit.Acted,
		ChanceSteps:             unit.ChanceSteps,
		ChanceStepsMax:          unit.ChanceStepsMax,
		SupportDefendCharges:    unit.SupportDefendCharges,
		SupportDefendChargesMax: unit.SupportDefendChargesMax,
		SupportAttackCharges:    unit.SupportAttackCharges,
		SupportAttackChargesMax: unit.SupportAttackChargesMax,
		HasShield:               unit.HasShield,
		SupportDefendWhenAttack: unit.SupportDefendWhenAttack,
		Ammo:                    make(map[string]int, len(unit.Ammo)),
		Debuffs:                 make([]protocol.Debuff, 0, len(unit.Debuffs)),
	}
	for _, weapon := range unit.Mech.Weapons {
		out.Mech.Weapons = append(out.Mech.Weapons, encodeWeapon(weapon))
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

func encodeWeapon(weapon battle.Weapon) protocol.Weapon {
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
		DebuffMagnitude: weapon.DebuffMagnitude,
	}
	if weapon.DebuffKind != "" {
		kind := weapon.DebuffKind
		out.DebuffKind = &kind
	}
	for _, category := range weapon.Categories {
		out.Categories = append(out.Categories, string(category))
	}
	return out
}

func encodeSkill(skill battle.Skill) protocol.Skill {
	return protocol.Skill{
		Kind:            protocol.SkillKind(skill.Kind),
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

func decodeFootprint(unit *protocol.Unit) (battle.Footprint, error) {
	size := battle.Size{unit.Size[0], unit.Size[1]}
	for axis := range size {
		if size[axis] < 0 {
			return battle.Footprint{}, fmt.Errorf("unit %q carries the size %v", unit.UnitID, unit.Size)
		}
		if size[axis] == 0 {
			size[axis] = 1
		}
	}
	return battle.Footprint{Anchor: DecodeCell(unit.Pos), Size: size}, nil
}

func decodeBounds(bounds *protocol.Bounds) (battle.Bounds, error) {
	if bounds == nil {
		return battle.Bounds{}, fmt.Errorf("the state carries no bounds")
	}
	return battle.Bounds{Low: DecodeCell(bounds[0]), High: DecodeCell(bounds[1])}, nil
}

func DecodeInit(request *protocol.InitRequest) (*Board, error) {
	if request.Board.Width < 1 || request.Board.Height < 1 {
		return nil, fmt.Errorf("the board %dx%d holds no cell", request.Board.Width, request.Board.Height)
	}
	units, err := decodeUnits(request.Enemies)
	if err != nil {
		return nil, err
	}
	bounds := battle.Bounds{High: battle.Cell{request.Board.Width - 1, request.Board.Height - 1}}
	for index := range units {
		fillMaxima(&units[index])
		if err := checkEnemy(&units[index], bounds); err != nil {
			return nil, err
		}
	}
	for _, entry := range request.Board.TerrainCells {
		cell := DecodeCell(entry.Cell)
		if !cellFootprint(cell).Within(bounds) {
			return nil, fmt.Errorf("the terrain cell %v stands outside the board", cell)
		}
	}
	b, err := New(bounds, units)
	if err != nil {
		return nil, err
	}
	if b.defaultTerrain, err = decodeTerrain(request.Board.Terrain); err != nil {
		return nil, err
	}
	if b.terrainCells, err = decodeTerrainCells(request.Board.TerrainCells); err != nil {
		return nil, err
	}
	b.phase = battle.FactionAlly
	b.turn = 1
	return b, nil
}

// A maximum that the payload leaves at zero comes from the pairing. An
// explicit value stands: an ability of the pilot or of the mech can lift the
// maximum above the base data (issue #77).
func fillMaxima(unit *battle.Unit) {
	if unit.MaxHP == 0 {
		unit.MaxHP = unit.Mech.HP
	}
	if unit.ENMax == 0 {
		unit.ENMax = unit.Mech.EN
	}
	if unit.SPMax == 0 {
		unit.SPMax = unit.Pilot.SP
	}
}

func checkEnemy(unit *battle.Unit, bounds battle.Bounds) error {
	if unit.Faction != battle.FactionEnemy {
		return fmt.Errorf("the unit %q of 'enemies' carries the faction %q",
			unit.ID, EncodeFaction(unit.Faction))
	}
	if !unit.Footprint.Within(bounds) {
		return fmt.Errorf("the unit %q stands outside the board", unit.ID)
	}
	return nil
}

func (b *Board) State() protocol.BattleState {
	bounds := protocol.Bounds{EncodeCell(b.bounds.Low), EncodeCell(b.bounds.High)}
	return protocol.BattleState{
		Units:         EncodeUnits(b.units),
		Phase:         wireFactions[b.phase],
		Turn:          b.turn,
		Bounds:        &bounds,
		PendingEvents: []string{},
		FiredEvents:   []string{},
		Terrain:       b.defaultTerrain.String(),
		TerrainCells:  encodeTerrainCells(b.terrainCells),
	}
}

func encodeTerrainCells(cells map[battle.Cell]battle.Terrain) []protocol.TerrainCell {
	declared := make(CellSet, len(cells))
	for cell := range cells {
		declared[cell] = true
	}
	out := make([]protocol.TerrainCell, 0, len(cells))
	for _, cell := range SortedCells(declared) {
		out = append(out, protocol.TerrainCell{Cell: EncodeCell(cell), Terrain: cells[cell].String()})
	}
	return out
}

func DecodeOutcomes(labels []string) ([]bool, error) {
	out := make([]bool, 0, len(labels))
	for index, label := range labels {
		switch label {
		case "hit":
			out = append(out, true)
		case "miss":
			out = append(out, false)
		default:
			return nil, fmt.Errorf("outcome %d is %q, and the contract holds 'hit' and 'miss'", index, label)
		}
	}
	return out, nil
}

func EncodeResolution(resolution battle.Resolution) []any {
	out := make([]any, 0, len(resolution.Trace)+len(resolution.Rotations))
	for _, strike := range resolution.Trace {
		out = append(out, protocol.StrikeEvent{
			Event: "strike", Strike: string(strike.Kind),
			ShooterID: strike.ShooterID, StruckID: strike.StruckID, Weapon: strike.Weapon,
			Landed: strike.Landed, Damage: strike.Damage, Killed: strike.Killed,
		})
	}
	for _, rotation := range resolution.Rotations {
		out = append(out, protocol.PhaseEvent{Event: "phase", Turn: rotation.Turn, Phase: wireFactions[rotation.Phase]})
	}
	return out
}

func (b *Board) Summary() protocol.BoardSummary {
	out := protocol.BoardSummary{
		Turn: b.turn, Phase: wireFactions[b.phase],
		Pending: []string{}, Gone: []protocol.Faction{},
	}
	for _, unit := range b.pending(b.phase) {
		out.Pending = append(out.Pending, unit.ID)
	}
	for _, faction := range b.gone() {
		out.Gone = append(out.Gone, wireFactions[faction])
	}
	return out
}
