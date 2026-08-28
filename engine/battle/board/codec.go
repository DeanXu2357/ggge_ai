package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var factions = map[protocol.Faction]faction{
	protocol.FactionAlly:       factionAlly,
	protocol.FactionEnemy:      factionEnemy,
	protocol.FactionThirdParty: factionThirdParty,
}

var actionKinds = map[protocol.ActionKind]actionKind{
	protocol.ActionAttack:     actionAttack,
	protocol.ActionMapAttack:  actionMapAttack,
	protocol.ActionReposition: actionReposition,
	protocol.ActionStandby:    actionStandby,
}

var affectsKinds = map[protocol.SkillAffects]skillAffects{
	protocol.AffectsAlly:  affectsAlly,
	protocol.AffectsEnemy: affectsEnemy,
	protocol.AffectsAll:   affectsAll,
}

var wireKinds = map[actionKind]protocol.ActionKind{
	actionAttack:     protocol.ActionAttack,
	actionMapAttack:  protocol.ActionMapAttack,
	actionReposition: protocol.ActionReposition,
	actionStandby:    protocol.ActionStandby,
}

var skillSources = map[protocol.SkillSource]skillSource{
	protocol.SourcePilot: sourcePilot,
	protocol.SourceCrew:  sourceCrew,
	protocol.SourceMech:  sourceMech,
}

var decodedStances = map[protocol.Stance]stance{
	protocol.StanceDodge:   stanceDodge,
	protocol.StanceDefend:  stanceDefend,
	protocol.StanceCounter: stanceCounter,
	protocol.StanceNone:    stanceNone,
}

var wireFactions = map[faction]protocol.Faction{
	factionAlly:       protocol.FactionAlly,
	factionEnemy:      protocol.FactionEnemy,
	factionThirdParty: protocol.FactionThirdParty,
}

var wireAffects = map[skillAffects]protocol.SkillAffects{
	affectsAlly:  protocol.AffectsAlly,
	affectsEnemy: protocol.AffectsEnemy,
	affectsAll:   protocol.AffectsAll,
}

var wireSources = map[skillSource]protocol.SkillSource{
	sourcePilot: protocol.SourcePilot,
	sourceCrew:  protocol.SourceCrew,
	sourceMech:  protocol.SourceMech,
}

var wireStances = map[stance]protocol.Stance{
	stanceDodge:   protocol.StanceDodge,
	stanceDefend:  protocol.StanceDefend,
	stanceCounter: protocol.StanceCounter,
	stanceNone:    protocol.StanceNone,
}

func encodeFaction(faction faction) protocol.Faction {
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
	b, err := newBoard(bounds, units)
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

func decodeTerrain(name string) (terrain, error) {
	if name == "" {
		return terrainSpace, nil
	}
	return parseTerrain(name)
}

func decodeTerrainCells(cells []protocol.TerrainCell) (map[cell]terrain, error) {
	if len(cells) == 0 {
		return nil, nil
	}
	out := make(map[cell]terrain, len(cells))
	for _, entry := range cells {
		kind, err := parseTerrain(entry.Terrain)
		if err != nil {
			return nil, fmt.Errorf("the cell %v carries a terrain outside the contract: %w",
				entry.Cell, err)
		}
		out[decodeCell(entry.Cell)] = kind
	}
	return out, nil
}

func decodeUnits(units []protocol.Unit) ([]unit, error) {
	if units == nil {
		return nil, nil
	}
	out := make([]unit, 0, len(units))
	for index := range units {
		unit, err := decodeUnit(&units[index])
		if err != nil {
			return nil, err
		}
		out = append(out, unit)
	}
	return out, nil
}

func decodeCell(wire protocol.Cell) cell {
	return cell{wire[0], wire[1]}
}

func encodeCell(cell cell) protocol.Cell {
	return protocol.Cell{cell[0], cell[1]}
}

func encodeCells(cells []cell) []protocol.Cell {
	out := make([]protocol.Cell, 0, len(cells))
	for _, cell := range cells {
		out = append(out, encodeCell(cell))
	}
	return out
}

func decodeUnit(wire *protocol.Unit) (unit, error) {
	faction, known := factions[wire.Faction]
	if !known {
		return unit{}, fmt.Errorf("unit %q carries the faction %q, which is not in the contract",
			wire.UnitID, wire.Faction)
	}
	footprint, err := decodeFootprint(wire)
	if err != nil {
		return unit{}, err
	}
	out := unit{
		ID:        wire.UnitID,
		Faction:   faction,
		Footprint: footprint,
		HP:        wire.HP,
		MaxHP:     wire.MaxHP,
		EN:        wire.EN,
		ENMax:     wire.ENMax,
		SP:        wire.SP,
		SPMax:     wire.SPMax,
		Pilot: pilot{
			Ranged:   wire.Pilot.Ranged,
			Melee:    wire.Pilot.Melee,
			Awaken:   wire.Pilot.Awaken,
			Defense:  wire.Pilot.Defense,
			Reaction: wire.Pilot.Reaction,
			SP:       wire.Pilot.SP,
		},
		Mech: mech{
			HP:        wire.Mech.HP,
			EN:        wire.Mech.EN,
			Attack:    wire.Mech.Attack,
			Defense:   wire.Mech.Defense,
			Mobility:  wire.Mech.Mobility,
			MoveRange: wire.Mech.MoveRange,
		},
		Acted:                   wire.Acted,
		ChanceSteps:             wire.ChanceSteps,
		ChanceStepsMax:          wire.ChanceStepsMax,
		SupportDefendCharges:    wire.SupportDefendCharges,
		SupportDefendChargesMax: wire.SupportDefendChargesMax,
		SupportAttackCharges:    wire.SupportAttackCharges,
		SupportAttackChargesMax: wire.SupportAttackChargesMax,
		HasShield:               wire.HasShield,
		SupportDefendWhenAttack: wire.SupportDefendWhenAttack,
	}
	if out.Mech.Weapons, err = decodeWeapons(wire.UnitID, wire.Mech.Weapons); err != nil {
		return unit{}, err
	}
	if wire.Skills != nil {
		out.Skills = make([]skill, 0, len(wire.Skills))
		for _, skill := range wire.Skills {
			decoded, err := decodeSkill(wire.UnitID, skill)
			if err != nil {
				return unit{}, err
			}
			out.Skills = append(out.Skills, decoded)
		}
	}
	if wire.Ammo != nil {
		out.Ammo = make(map[string]int, len(wire.Ammo))
		for name, count := range wire.Ammo {
			out.Ammo[name] = count
		}
	}
	if wire.Debuffs != nil {
		out.Debuffs = make([]debuff, 0, len(wire.Debuffs))
		for _, entry := range wire.Debuffs {
			out.Debuffs = append(out.Debuffs, debuff(entry))
		}
	}
	return out, nil
}

func decodeWeapons(unitID string, weapons []protocol.Weapon) ([]weapon, error) {
	if weapons == nil {
		return nil, nil
	}
	out := make([]weapon, 0, len(weapons))
	for index := range weapons {
		weapon, err := decodeWeapon(&weapons[index])
		if err != nil {
			return nil, fmt.Errorf("unit %q: %w", unitID, err)
		}
		out = append(out, weapon)
	}
	return out, nil
}

func decodeWeapon(wire *protocol.Weapon) (weapon, error) {
	out := weapon{
		Name:            wire.Name,
		Power:           wire.Power,
		Range:           radiusRange{Min: wire.RangeMin, Max: wire.RangeMax},
		ENCost:          wire.ENCost,
		Accuracy:        wire.Accuracy,
		CanCounter:      wire.CanCounter,
		MapWeapon:       wire.MapWeapon,
		UsableAfterMove: wire.UsableAfterMove,
		DebuffMagnitude: wire.DebuffMagnitude,
	}
	if wire.DebuffKind != nil {
		out.DebuffKind = *wire.DebuffKind
	}
	for _, name := range wire.Categories {
		category, err := parseWeaponCategory(name)
		if err != nil {
			return weapon{}, fmt.Errorf("the weapon %q carries %w", wire.Name, err)
		}
		out.Categories = append(out.Categories, category)
	}
	return out, nil
}

func decodeSkill(unitID string, wire protocol.Skill) (skill, error) {
	source, known := skillSources[wire.Source]
	if !known {
		return skill{}, fmt.Errorf("unit %q carries a skill of the source %q, which is not in the contract",
			unitID, wire.Source)
	}
	affects, known := affectsKinds[wire.Affects]
	if !known {
		return skill{}, fmt.Errorf("unit %q carries a skill that affects %q, which is not in the contract",
			unitID, wire.Affects)
	}
	return skill{
		Kind:            skillKind(wire.Kind),
		Source:          source,
		Amount:          cloneAmount(wire.Amount),
		Uses:            wire.Uses,
		EndsActivation:  wire.EndsActivation,
		UsableAfterMove: wire.UsableAfterMove,
		Range:           radiusRange{Min: wire.RangeMin, Max: wire.RangeMax},
		Blast:           wire.Blast,
		Affects:         affects,
	}, nil
}

func encodeCapabilities(capabilities capabilities) protocol.ActionsResponse {
	unit := capabilities.Unit
	out := protocol.ActionsResponse{
		Unit:      encodeUnitStatus(unit),
		MoveCells: encodeCells(capabilities.MoveCells),
		Weapons:   encodeWeapons(unit),
		Skills:    encodeSkills(unit.Skills),
	}
	if unit.Acted {
		out.Error = &protocol.Error{
			Code:    protocol.CodeAlreadyActed,
			Message: fmt.Sprintf("the unit %q acted in this turn", unit.ID),
		}
	}
	return out
}

func encodeUnitStatus(unit *unit) protocol.UnitStatus {
	return protocol.UnitStatus{
		UnitID:    unit.ID,
		Faction:   wireFactions[unit.Faction],
		Pos:       encodeCell(unit.Footprint.Anchor),
		Size:      protocol.Cell{unit.Footprint.Size[0], unit.Footprint.Size[1]},
		HP:        unit.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.EN,
		ENMax:     unit.ENMax,
		MoveRange: unit.Mech.MoveRange,
		Acted:     unit.Acted,
	}
}

func encodeWeapons(unit *unit) []protocol.WeaponEntry {
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

func encodeSkills(skills []skill) []protocol.SkillEntry {
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

func DecodeDecision(action *protocol.Decision) (decision, error) {
	kind, known := actionKinds[action.Kind]
	if !known {
		return decision{}, fmt.Errorf("%w: the action carries the kind %q",
			protocol.ErrOutsideContract, action.Kind)
	}
	out := decision{
		UnitID:           action.UnitID,
		Kind:             kind,
		TargetID:         decodeOptionalName(action.TargetID),
		Weapon:           decodeOptionalName(action.Weapon),
		Amount:           cloneAmount(action.Amount),
		SupportDefender:  decodeOptionalName(action.SupportDefender),
		SupportAttackers: append([]string(nil), action.SupportAttackers...),
	}
	if action.ResponseAttack != nil {
		responseAttack, err := decodeResponseAttack(*action.ResponseAttack)
		if err != nil {
			return decision{}, err
		}
		out.ResponseAttack = &responseAttack
	}
	if action.MoveTo != nil {
		cell := decodeCell(*action.MoveTo)
		out.MoveTo = &cell
	}
	if action.Aim != nil {
		aim := decodeCell(*action.Aim)
		out.Aim = &aim
	}
	return out, nil
}

func decodeResponseAttack(wire protocol.ResponseAttack) (responseAttack, error) {
	stance, known := decodedStances[wire.Stance]
	if !known {
		return responseAttack{}, fmt.Errorf("%w: the response attack carries the stance %q",
			protocol.ErrOutsideContract, wire.Stance)
	}
	return responseAttack{
		Stance:           stance,
		Weapon:           decodeOptionalName(wire.Weapon),
		SupportDefender:  decodeOptionalName(wire.SupportDefender),
		SupportAttackers: append([]string(nil), wire.SupportAttackers...),
	}, nil
}

func decodeOptionalName(name *string) string {
	if name == nil {
		return ""
	}
	return *name
}

func encodeEngagement(engagement engagement) protocol.ResponseAttacksResponse {
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

func encodeResponseAttackOptions(options []responseAttackOption) []protocol.ResponseAttackOption {
	out := make([]protocol.ResponseAttackOption, 0, len(options))
	for _, option := range options {
		entry := protocol.ResponseAttackOption{
			Stance:   wireStances[option.Stance],
			Weapon:   encodeOptionalName(option.Weapon),
			Incoming: encodeForecast(option.Incoming),
		}
		if option.Counter != nil {
			counter := encodeForecast(*option.Counter)
			entry.Counter = &counter
		}
		out = append(out, entry)
	}
	return out
}

// The wire carries no integer type, so the damage goes out as a number.
func encodeForecast(forecast forecast) protocol.Forecast {
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

func encodeSupportDefenders(options []supportDefendOption) []protocol.SupportDefendOption {
	out := make([]protocol.SupportDefendOption, 0, len(options))
	for _, option := range options {
		out = append(out, protocol.SupportDefendOption{
			UnitID:   option.Unit.ID,
			Incoming: encodeForecast(option.Incoming),
		})
	}
	return out
}

func encodeSupportAttackers(options []supportAttackOption) []protocol.SupportAttackOption {
	out := make([]protocol.SupportAttackOption, 0, len(options))
	for _, option := range options {
		out = append(out, protocol.SupportAttackOption{
			UnitID: option.Unit.ID,
			Weapon: option.Weapon.Name,
			Strike: encodeForecast(option.Strike),
		})
	}
	return out
}

func encodeUnits(units []unit) []protocol.Unit {
	out := make([]protocol.Unit, 0, len(units))
	for _, unit := range units {
		out = append(out, encodeUnit(unit))
	}
	return out
}

// A list and a map hold no null on the wire, so an empty one is an empty
// list and an empty object.
func encodeUnit(unit unit) protocol.Unit {
	out := protocol.Unit{
		UnitID:  unit.ID,
		Faction: wireFactions[unit.Faction],
		Pos:     encodeCell(unit.Footprint.Anchor),
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

func encodeWeapon(weapon weapon) protocol.Weapon {
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

func encodeSkill(skill skill) protocol.Skill {
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

func decodeFootprint(unit *protocol.Unit) (footprint, error) {
	size := size{unit.Size[0], unit.Size[1]}
	for axis := range size {
		if size[axis] < 0 {
			return footprint{}, fmt.Errorf("unit %q carries the size %v", unit.UnitID, unit.Size)
		}
		if size[axis] == 0 {
			size[axis] = 1
		}
	}
	return footprint{Anchor: decodeCell(unit.Pos), Size: size}, nil
}

func decodeBounds(wire *protocol.Bounds) (bounds, error) {
	if wire == nil {
		return bounds{}, fmt.Errorf("the state carries no bounds")
	}
	return bounds{Low: decodeCell(wire[0]), High: decodeCell(wire[1])}, nil
}

func DecodeInit(request *protocol.InitRequest) (*Board, error) {
	if request.Board.Width < 1 || request.Board.Height < 1 {
		return nil, fmt.Errorf("the board %dx%d holds no cell", request.Board.Width, request.Board.Height)
	}
	units, err := decodeUnits(request.Enemies)
	if err != nil {
		return nil, err
	}
	bounds := bounds{High: cell{request.Board.Width - 1, request.Board.Height - 1}}
	for index := range units {
		fillMaxima(&units[index])
		if err := checkEnemy(&units[index], bounds); err != nil {
			return nil, err
		}
	}
	for _, entry := range request.Board.TerrainCells {
		cell := decodeCell(entry.Cell)
		if !cellFootprint(cell).within(bounds) {
			return nil, fmt.Errorf("the terrain cell %v stands outside the board", cell)
		}
	}
	b, err := newBoard(bounds, units)
	if err != nil {
		return nil, err
	}
	if b.defaultTerrain, err = decodeTerrain(request.Board.Terrain); err != nil {
		return nil, err
	}
	if b.terrainCells, err = decodeTerrainCells(request.Board.TerrainCells); err != nil {
		return nil, err
	}
	b.phase = factionAlly
	b.turn = 1
	return b, nil
}

// A maximum that the payload leaves at zero comes from the pairing. An
// explicit value stands: an ability of the pilot or of the mech can lift the
// maximum above the base data (issue #77).
func fillMaxima(unit *unit) {
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

func checkEnemy(unit *unit, bounds bounds) error {
	if unit.Faction != factionEnemy {
		return fmt.Errorf("the unit %q of 'enemies' carries the faction %q",
			unit.ID, encodeFaction(unit.Faction))
	}
	if !unit.Footprint.within(bounds) {
		return fmt.Errorf("the unit %q stands outside the board", unit.ID)
	}
	return nil
}

func (b *Board) State() protocol.BattleState {
	bounds := protocol.Bounds{encodeCell(b.bounds.Low), encodeCell(b.bounds.High)}
	return protocol.BattleState{
		Units:         encodeUnits(b.units),
		Phase:         wireFactions[b.phase],
		Turn:          b.turn,
		Bounds:        &bounds,
		PendingEvents: []string{},
		FiredEvents:   []string{},
		Terrain:       b.defaultTerrain.String(),
		TerrainCells:  encodeTerrainCells(b.terrainCells),
	}
}

func encodeTerrainCells(cells map[cell]terrain) []protocol.TerrainCell {
	declared := make(cellSet, len(cells))
	for cell := range cells {
		declared[cell] = true
	}
	out := make([]protocol.TerrainCell, 0, len(cells))
	for _, cell := range sortedCells(declared) {
		out = append(out, protocol.TerrainCell{Cell: encodeCell(cell), Terrain: cells[cell].String()})
	}
	return out
}

func encodeResolution(resolution resolution) []any {
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
