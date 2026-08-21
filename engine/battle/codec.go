package battle

import (
	"encoding/json"
	"fmt"
	"maps"
	"slices"

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
	board.PendingEvents = slices.Clone(state.PendingEvents)
	board.FiredEvents = slices.Clone(state.FiredEvents)
	return board, nil
}

// DecodeInit builds the board of one battle from the request of 'init': the
// map with its terrain, the units that the stage puts on it, the rules and the
// stage event table. The battle starts on turn 1, in the ally phase, with every
// event of the table waiting. The ally units arrive with the deploy commands.
func DecodeInit(request *protocol.InitRequest) (*Board, error) {
	if request.Board.Width <= 0 || request.Board.Height <= 0 {
		return nil, fmt.Errorf("the board carries the size %d by %d",
			request.Board.Width, request.Board.Height)
	}
	units, err := decodeUnits(request.Enemies)
	if err != nil {
		return nil, err
	}
	for _, unit := range units {
		if unit.Faction == FactionAlly {
			return nil, fmt.Errorf("the unit %q of the field \"enemies\" is of the ally side",
				unit.ID)
		}
	}
	rules, err := DecodeRules(request.Rules)
	if err != nil {
		return nil, err
	}
	bounds := Bounds{
		Low:  Cell{0, 0},
		High: Cell{request.Board.Width - 1, request.Board.Height - 1},
	}
	board, err := NewBoard(bounds, units, rules)
	if err != nil {
		return nil, err
	}
	if board.DefaultTerrain, err = decodeTerrain(request.Board.Terrain); err != nil {
		return nil, err
	}
	if board.TerrainCells, err = decodeTerrainCells(request.Board.TerrainCells); err != nil {
		return nil, err
	}
	if board.Events, err = DecodeEvents(request.Events); err != nil {
		return nil, err
	}
	board.PendingEvents = slices.Sorted(maps.Keys(board.Events))
	board.Phase = FactionAlly
	board.Turn = 1
	return board, nil
}

// EncodeState writes the board back to the wire. The terrain fields stay absent
// while the whole map is in space and no cell takes another kind, so a state
// that declared no terrain reads back as the same bytes.
func EncodeState(board *Board) protocol.BattleState {
	out := protocol.BattleState{
		Units:         EncodeUnits(board.Units),
		Phase:         wireFactions[board.Phase],
		Turn:          board.Turn,
		Bounds:        &protocol.Bounds{EncodeCell(board.Bounds.Low), EncodeCell(board.Bounds.High)},
		PendingEvents: eventNames(board.PendingEvents),
		FiredEvents:   eventNames(board.FiredEvents),
		TerrainCells:  encodeTerrainCells(board.TerrainCells),
	}
	if board.DefaultTerrain != TerrainSpace {
		out.Terrain = board.DefaultTerrain.String()
	}
	return out
}

func eventNames(ids []string) []string {
	if ids == nil {
		return []string{}
	}
	return ids
}

// The overrides come out in one order, because a map holds none.
func encodeTerrainCells(cells map[Cell]Terrain) []protocol.TerrainCell {
	if len(cells) == 0 {
		return nil
	}
	taken := make(CellSet, len(cells))
	for cell := range cells {
		taken[cell] = true
	}
	out := make([]protocol.TerrainCell, 0, len(cells))
	for _, cell := range SortedCells(taken) {
		out = append(out, protocol.TerrainCell{
			Cell:    EncodeCell(cell),
			Terrain: cells[cell].String(),
		})
	}
	return out
}

// DecodeOutcomes reads the outcome list of the forced dice. Every chance node
// of the engine settles one shot, so the label set holds 'hit' and 'miss'.
func DecodeOutcomes(labels []string) ([]bool, error) {
	out := make([]bool, 0, len(labels))
	for _, label := range labels {
		switch label {
		case protocol.OutcomeHit:
			out = append(out, true)
		case protocol.OutcomeMiss:
			out = append(out, false)
		default:
			return nil, fmt.Errorf("the outcome %q is not in the contract", label)
		}
	}
	return out, nil
}

// DecodeEvents reads the stage event table. A trigger or an effect outside the
// contract stops the decode: the turn cycle runs the table at every activation,
// and an entry that it cannot run is a stage that it cannot play.
func DecodeEvents(events protocol.EventTable) (EventTable, error) {
	if len(events) == 0 {
		return nil, nil
	}
	out := make(EventTable, len(events))
	for id, event := range events {
		decoded, err := decodeEvent(id, event)
		if err != nil {
			return nil, err
		}
		out[id] = decoded
	}
	return out, nil
}

func decodeEvent(id string, event protocol.StageEvent) (StageEvent, error) {
	trigger, err := decodeTrigger(event.Trigger)
	if err != nil {
		return StageEvent{}, fmt.Errorf("the event %q: %w", id, err)
	}
	effect, err := decodeEffect(event.Effect)
	if err != nil {
		return StageEvent{}, fmt.Errorf("the event %q: %w", id, err)
	}
	return StageEvent{ID: id, Trigger: trigger, Effect: effect}, nil
}

func decodeTrigger(payload json.RawMessage) (Trigger, error) {
	var raw struct {
		Type       TriggerKind `json:"type"`
		UnitID     string      `json:"uid"`
		WithinTurn *int        `json:"within_turn"`
		Turn       int         `json:"turn"`
	}
	if err := json.Unmarshal(payload, &raw); err != nil {
		return Trigger{}, fmt.Errorf("the trigger: %w", err)
	}
	if raw.Type != TriggerKill && raw.Type != TriggerTurnStart {
		return Trigger{}, fmt.Errorf("the trigger %q is not in the contract", raw.Type)
	}
	return Trigger{
		Kind:       raw.Type,
		UnitID:     raw.UnitID,
		WithinTurn: raw.WithinTurn,
		Turn:       raw.Turn,
	}, nil
}

// An absent multiplier of a weaken effect is 1.0: the effect leaves that value
// of the mech as it was.
func decodeEffect(payload json.RawMessage) (Effect, error) {
	var raw struct {
		Type              EffectKind      `json:"type"`
		Units             []protocol.Unit `json:"units"`
		UnitIDs           []string        `json:"uids"`
		AttackMultiplier  *float64        `json:"attack_multiplier"`
		DefenseMultiplier *float64        `json:"defense_multiplier"`
	}
	if err := json.Unmarshal(payload, &raw); err != nil {
		return Effect{}, fmt.Errorf("the effect: %w", err)
	}
	if raw.Type != EffectSpawn && raw.Type != EffectWeaken {
		return Effect{}, fmt.Errorf("the effect %q is not in the contract", raw.Type)
	}
	units, err := decodeUnits(raw.Units)
	if err != nil {
		return Effect{}, err
	}
	return Effect{
		Kind:              raw.Type,
		Units:             units,
		UnitIDs:           raw.UnitIDs,
		AttackMultiplier:  scaleOf(raw.AttackMultiplier),
		DefenseMultiplier: scaleOf(raw.DefenseMultiplier),
	}, nil
}

func scaleOf(value *float64) float64 {
	if value == nil {
		return 1
	}
	return *value
}

// EncodeRules writes the rules of the session back to the wire.
func EncodeRules(rules Rules) protocol.Rules {
	return protocol.Rules(rules)
}

// EncodeResolution writes the resolution in order: the strikes of the
// engagement, then the stage events that the outcome fired, then the phase
// boundaries that the turn cycle crossed.
func EncodeResolution(resolution Resolution) []any {
	out := make([]any, 0, len(resolution.Trace)+len(resolution.Fired)+len(resolution.Rotations))
	for _, strike := range resolution.Trace {
		out = append(out, protocol.StrikeEvent{
			Kind:      string(strike.Kind),
			ShooterID: strike.ShooterID,
			StruckID:  strike.StruckID,
			Weapon:    strike.Weapon,
			Landed:    strike.Landed,
			Damage:    strike.Damage,
			Killed:    strike.Killed,
		})
	}
	for _, id := range resolution.Fired {
		out = append(out, protocol.StageEventFired{Kind: protocol.EventStageEvent, EventID: id})
	}
	for _, rotation := range resolution.Rotations {
		for _, id := range rotation.Fired {
			out = append(out, protocol.StageEventFired{Kind: protocol.EventStageEvent, EventID: id})
		}
		out = append(out, protocol.PhaseEvent{
			Kind:  protocol.EventPhase,
			Turn:  rotation.Turn,
			Phase: wireFactions[rotation.Phase],
		})
	}
	return out
}

// EncodeSummary writes what the board looks like after a command that changed
// it.
func EncodeSummary(board *Board) protocol.BoardSummary {
	pending := board.PendingUnits(board.Phase)
	out := protocol.BoardSummary{
		Turn:    board.Turn,
		Phase:   wireFactions[board.Phase],
		Pending: make([]string, 0, len(pending)),
	}
	for _, unit := range pending {
		out.Pending = append(out.Pending, unit.ID)
	}
	return out
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
// gives the defaults, and a payload that carries the rules carries every field:
// a field that the payload omits decodes to zero, and no rule value of the
// mechanism is zero (docs/reference/combat-formulas.md).
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
