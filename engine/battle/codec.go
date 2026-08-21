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
	board, err := NewBoard(bounds, units)
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
		MoveRange:            unit.MoveRange,
		Acted:                unit.Acted,
		SupportDefendCharges: unit.SupportDefendCharges,
		SupportAttackCharges: unit.SupportAttackCharges,
		HasShield:            unit.HasShield,
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
		Range:           RadiusRange{Min: weapon.RangeMin, Max: weapon.RangeMax},
		ENCost:          weapon.ENCost,
		Accuracy:        weapon.Accuracy,
		CanCounter:      weapon.CanCounter,
		MapWeapon:       weapon.MapWeapon,
		UsableAfterMove: weapon.UsableAfterMove,
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
	affects, known := skillAffects[skill.Affects]
	if !known {
		return Skill{}, fmt.Errorf("unit %q carries a skill that affects %q, which is not in the contract",
			unitID, skill.Affects)
	}
	return Skill{
		Kind:            kind,
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
// settles no die and carries no reaction, so 'hit', 'counter_hit',
// 'support_hit' and 'reaction' stay null.
func EncodeDecision(decision Decision) protocol.Decision {
	return protocol.Decision{
		UnitID:   decision.UnitID,
		Kind:     wireKinds[decision.Kind],
		MoveTo:   encodeOptionalCell(decision.MoveTo),
		TargetID: encodeOptionalName(decision.TargetID),
		Weapon:   encodeOptionalName(decision.Weapon),
		Amount:   cloneAmount(decision.Amount),
		Support:  decision.Support,
		Aim:      encodeOptionalCell(decision.Aim),
	}
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
