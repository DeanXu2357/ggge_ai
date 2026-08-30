package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

var factions = map[protocol.Faction]state.Faction{
	protocol.FactionAlly:       state.FactionAlly,
	protocol.FactionEnemy:      state.FactionEnemy,
	protocol.FactionThirdParty: state.FactionThirdParty,
}

var actionKinds = map[protocol.ActionKind]actionKind{
	protocol.ActionAttack:     actionAttack,
	protocol.ActionMapAttack:  actionMapAttack,
	protocol.ActionReposition: actionReposition,
	protocol.ActionStandby:    actionStandby,
}

var affectsKinds = map[protocol.SkillAffects]state.SkillAffects{
	protocol.AffectsAlly:  state.AffectsAlly,
	protocol.AffectsEnemy: state.AffectsEnemy,
	protocol.AffectsAll:   state.AffectsAll,
}

var wireKinds = map[actionKind]protocol.ActionKind{
	actionAttack:     protocol.ActionAttack,
	actionMapAttack:  protocol.ActionMapAttack,
	actionReposition: protocol.ActionReposition,
	actionStandby:    protocol.ActionStandby,
}

var skillSources = map[protocol.SkillSource]state.SkillSource{
	protocol.SourcePilot: state.SourcePilot,
	protocol.SourceCrew:  state.SourceCrew,
	protocol.SourceMech:  state.SourceMech,
}

var decodedStances = map[protocol.Stance]stance{
	protocol.StanceDodge:   stanceDodge,
	protocol.StanceDefend:  stanceDefend,
	protocol.StanceCounter: stanceCounter,
	protocol.StanceNone:    stanceNone,
}

var wireFactions = map[state.Faction]protocol.Faction{
	state.FactionAlly:       protocol.FactionAlly,
	state.FactionEnemy:      protocol.FactionEnemy,
	state.FactionThirdParty: protocol.FactionThirdParty,
}

var wireAffects = map[state.SkillAffects]protocol.SkillAffects{
	state.AffectsAlly:  protocol.AffectsAlly,
	state.AffectsEnemy: protocol.AffectsEnemy,
	state.AffectsAll:   protocol.AffectsAll,
}

var wireSources = map[state.SkillSource]protocol.SkillSource{
	state.SourcePilot: protocol.SourcePilot,
	state.SourceCrew:  protocol.SourceCrew,
	state.SourceMech:  protocol.SourceMech,
}

var wireStances = map[stance]protocol.Stance{
	stanceDodge:   protocol.StanceDodge,
	stanceDefend:  protocol.StanceDefend,
	stanceCounter: protocol.StanceCounter,
	stanceNone:    protocol.StanceNone,
}

func encodeFaction(faction state.Faction) protocol.Faction {
	return wireFactions[faction]
}

func DecodeState(wire *protocol.BattleState) (*Board, error) {
	if wire == nil {
		return nil, fmt.Errorf("the payload carries no state")
	}
	bounds, err := decodeBounds(wire.Bounds)
	if err != nil {
		return nil, err
	}
	units, err := decodeUnits(wire.Units)
	if err != nil {
		return nil, err
	}
	b, err := newBoard(bounds, units)
	if err != nil {
		return nil, err
	}
	if b.state.DefaultTerrain, err = decodeTerrain(wire.Terrain); err != nil {
		return nil, err
	}
	if b.state.TerrainCells, err = decodeTerrainCells(wire.TerrainCells); err != nil {
		return nil, err
	}
	phase, known := factions[wire.Phase]
	if !known {
		return nil, fmt.Errorf("the state carries the phase %q, which is not in the contract",
			wire.Phase)
	}
	b.state.Phase = phase
	b.state.Turn = wire.Turn
	return b, nil
}

func terrainName(kind state.Terrain) string {
	if kind < 0 || int(kind) >= len(state.Names) {
		return fmt.Sprintf("terrain(%d)", int(kind))
	}
	return state.Names[kind]
}

func parseTerrain(name string) (state.Terrain, error) {
	for kind, known := range state.Names {
		if known == name {
			return state.Terrain(kind), nil
		}
	}
	return 0, fmt.Errorf("the terrain %q is not in the contract", name)
}

func decodeTerrain(name string) (state.Terrain, error) {
	if name == "" {
		return state.TerrainSpace, nil
	}
	return parseTerrain(name)
}

func decodeTerrainCells(cells []protocol.TerrainCell) (map[state.Cell]state.Terrain, error) {
	if len(cells) == 0 {
		return nil, nil
	}
	out := make(map[state.Cell]state.Terrain, len(cells))
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

func decodeUnits(units []protocol.Unit) ([]state.Unit, error) {
	if units == nil {
		return nil, nil
	}
	out := make([]state.Unit, 0, len(units))
	for index := range units {
		unit, err := decodeUnit(&units[index])
		if err != nil {
			return nil, err
		}
		out = append(out, unit)
	}
	return out, nil
}

func decodeCell(wire protocol.Cell) state.Cell {
	return state.Cell{wire[0], wire[1]}
}

func encodeCell(cell state.Cell) protocol.Cell {
	return protocol.Cell{cell[0], cell[1]}
}

func encodeCells(cells []state.Cell) []protocol.Cell {
	out := make([]protocol.Cell, 0, len(cells))
	for _, cell := range cells {
		out = append(out, encodeCell(cell))
	}
	return out
}

func decodeUnit(wire *protocol.Unit) (state.Unit, error) {
	faction, known := factions[wire.Faction]
	if !known {
		return state.Unit{}, fmt.Errorf("unit %q carries the faction %q, which is not in the contract",
			wire.UnitID, wire.Faction)
	}
	footprint, err := decodeFootprint(wire)
	if err != nil {
		return state.Unit{}, err
	}
	out := state.Unit{
		ID:                      wire.UnitID,
		Faction:                 faction,
		Footprint:               footprint,
		HP:                      wire.HP,
		MaxHP:                   wire.MaxHP,
		EN:                      wire.EN,
		ENMax:                   wire.ENMax,
		SP:                      wire.SP,
		SPMax:                   wire.SPMax,
		Pilot:                   decodePilot(&wire.Pilot),
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
	if out.Mech, err = decodeMech(wire.UnitID, &wire.Mech); err != nil {
		return state.Unit{}, err
	}
	if wire.Skills != nil {
		out.Skills = make([]state.Skill, 0, len(wire.Skills))
		for _, skill := range wire.Skills {
			decoded, err := decodeSkill(wire.UnitID, skill)
			if err != nil {
				return state.Unit{}, err
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
		out.Debuffs = make([]state.Debuff, 0, len(wire.Debuffs))
		for _, entry := range wire.Debuffs {
			out.Debuffs = append(out.Debuffs, state.Debuff(entry))
		}
	}
	return out, nil
}

func decodeSkill(unitID string, wire protocol.Skill) (state.Skill, error) {
	source, known := skillSources[wire.Source]
	if !known {
		return state.Skill{}, fmt.Errorf("unit %q carries a skill of the source %q, which is not in the contract",
			unitID, wire.Source)
	}
	affects, known := affectsKinds[wire.Affects]
	if !known {
		return state.Skill{}, fmt.Errorf("unit %q carries a skill that affects %q, which is not in the contract",
			unitID, wire.Affects)
	}
	return state.Skill{
		Kind:            state.SkillKind(wire.Kind),
		Source:          source,
		Amount:          cloneAmount(wire.Amount),
		Uses:            wire.Uses,
		EndsActivation:  wire.EndsActivation,
		UsableAfterMove: wire.UsableAfterMove,
		Range:           def.RadiusRange{Min: wire.RangeMin, Max: wire.RangeMax},
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

func encodeUnitStatus(unit *state.Unit) protocol.UnitStatus {
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

func encodeWeapons(unit *state.Unit) []protocol.WeaponEntry {
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

func encodeSkills(skills []state.Skill) []protocol.SkillEntry {
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

func encodeUnits(units []state.Unit) []protocol.Unit {
	out := make([]protocol.Unit, 0, len(units))
	for _, unit := range units {
		out = append(out, encodeUnit(unit))
	}
	return out
}

// A list and a map hold no null on the wire, so an empty one is an empty
// list and an empty object.
func encodeUnit(unit state.Unit) protocol.Unit {
	out := protocol.Unit{
		UnitID:                  unit.ID,
		Faction:                 wireFactions[unit.Faction],
		Pos:                     encodeCell(unit.Footprint.Anchor),
		Size:                    protocol.Cell{unit.Footprint.Size[0], unit.Footprint.Size[1]},
		HP:                      unit.HP,
		MaxHP:                   unit.MaxHP,
		EN:                      unit.EN,
		ENMax:                   unit.ENMax,
		SP:                      unit.SP,
		SPMax:                   unit.SPMax,
		Pilot:                   encodePilot(unit.Pilot),
		Mech:                    encodeMech(unit.Mech),
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

func encodeSkill(skill state.Skill) protocol.Skill {
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

func cloneAmount(amount *float64) *float64 {
	if amount == nil {
		return nil
	}
	out := *amount
	return &out
}

func cellFootprint(cell state.Cell) state.Footprint {
	return state.Footprint{Anchor: cell, Size: state.Size{1, 1}}
}

func decodeFootprint(unit *protocol.Unit) (state.Footprint, error) {
	size := state.Size{unit.Size[0], unit.Size[1]}
	for axis := range size {
		if size[axis] < 0 {
			return state.Footprint{}, fmt.Errorf("unit %q carries the size %v", unit.UnitID, unit.Size)
		}
		if size[axis] == 0 {
			size[axis] = 1
		}
	}
	return state.Footprint{Anchor: decodeCell(unit.Pos), Size: size}, nil
}

func decodeBounds(wire *protocol.Bounds) (state.Bounds, error) {
	if wire == nil {
		return state.Bounds{}, fmt.Errorf("the state carries no bounds")
	}
	return state.Bounds{Low: decodeCell(wire[0]), High: decodeCell(wire[1])}, nil
}

func DecodeInit(request *protocol.InitRequest) (*Board, error) {
	if request.Board.Width < 1 || request.Board.Height < 1 {
		return nil, fmt.Errorf("the board %dx%d holds no cell", request.Board.Width, request.Board.Height)
	}
	units, err := decodeUnits(request.Enemies)
	if err != nil {
		return nil, err
	}
	bounds := state.Bounds{High: state.Cell{request.Board.Width - 1, request.Board.Height - 1}}
	for index := range units {
		fillMaxima(&units[index])
		if err := checkEnemy(&units[index], bounds); err != nil {
			return nil, err
		}
	}
	for _, entry := range request.Board.TerrainCells {
		cell := decodeCell(entry.Cell)
		if !cellFootprint(cell).Within(bounds) {
			return nil, fmt.Errorf("the terrain cell %v stands outside the board", cell)
		}
	}
	b, err := newBoard(bounds, units)
	if err != nil {
		return nil, err
	}
	if b.state.DefaultTerrain, err = decodeTerrain(request.Board.Terrain); err != nil {
		return nil, err
	}
	if b.state.TerrainCells, err = decodeTerrainCells(request.Board.TerrainCells); err != nil {
		return nil, err
	}
	b.state.Phase = state.FactionAlly
	b.state.Turn = 1
	return b, nil
}

// A maximum that the payload leaves at zero comes from the pairing. An
// explicit value stands: an ability of the pilot or of the mech can lift the
// maximum above the base data (issue #77).
func fillMaxima(unit *state.Unit) {
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

func checkEnemy(unit *state.Unit, bounds state.Bounds) error {
	if unit.Faction != state.FactionEnemy {
		return fmt.Errorf("the unit %q of 'enemies' carries the faction %q",
			unit.ID, encodeFaction(unit.Faction))
	}
	if !unit.Footprint.Within(bounds) {
		return fmt.Errorf("the unit %q stands outside the board", unit.ID)
	}
	return nil
}

func (b *Board) State() protocol.BattleState {
	bounds := protocol.Bounds{encodeCell(b.state.Bounds.Low), encodeCell(b.state.Bounds.High)}
	return protocol.BattleState{
		Units:         encodeUnits(b.state.Units),
		Phase:         wireFactions[b.state.Phase],
		Turn:          b.state.Turn,
		Bounds:        &bounds,
		PendingEvents: []string{},
		FiredEvents:   []string{},
		Terrain:       terrainName(b.state.DefaultTerrain),
		TerrainCells:  encodeTerrainCells(b.state.TerrainCells),
	}
}

func encodeTerrainCells(cells map[state.Cell]state.Terrain) []protocol.TerrainCell {
	declared := make(geometry.CellSet, len(cells))
	for cell := range cells {
		declared[cell] = true
	}
	out := make([]protocol.TerrainCell, 0, len(cells))
	for _, cell := range geometry.SortedCells(declared) {
		out = append(out, protocol.TerrainCell{Cell: encodeCell(cell), Terrain: terrainName(cells[cell])})
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
		Turn: b.state.Turn, Phase: wireFactions[b.state.Phase],
		Pending: []string{}, Gone: []protocol.Faction{},
	}
	for _, unit := range b.pending(b.state.Phase) {
		out.Pending = append(out.Pending, unit.ID)
	}
	for _, faction := range b.gone() {
		out.Gone = append(out.Gone, wireFactions[faction])
	}
	return out
}
