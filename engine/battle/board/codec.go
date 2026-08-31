package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
)

var actionKinds = map[battle.ActionKind]engagement.ActionKind{
	battle.ActionAttack:     engagement.ActionAttack,
	battle.ActionMapAttack:  engagement.ActionMapAttack,
	battle.ActionReposition: engagement.ActionReposition,
	battle.ActionStandby:    engagement.ActionStandby,
}

var decodedStances = map[battle.Stance]engagement.Stance{
	battle.StanceDodge:   engagement.StanceDodge,
	battle.StanceDefend:  engagement.StanceDefend,
	battle.StanceCounter: engagement.StanceCounter,
	battle.StanceNone:    engagement.StanceNone,
}

var wireStances = map[engagement.Stance]battle.Stance{
	engagement.StanceDodge:   battle.StanceDodge,
	engagement.StanceDefend:  battle.StanceDefend,
	engagement.StanceCounter: battle.StanceCounter,
	engagement.StanceNone:    battle.StanceNone,
}

func decodeDecision(action *battle.Decision) (engagement.Decision, error) {
	kind, known := actionKinds[action.Kind]
	if !known {
		return engagement.Decision{}, fmt.Errorf("%w: the action carries the kind %q",
			battle.ErrOutsideContract, action.Kind)
	}
	out := engagement.Decision{
		UnitID:           action.UnitID,
		Kind:             kind,
		TargetID:         decodeOptionalName(action.TargetID),
		Weapon:           decodeOptionalName(action.Weapon),
		Amount:           battle.CloneAmount(action.Amount),
		SupportDefender:  decodeOptionalName(action.SupportDefender),
		SupportAttackers: append([]string(nil), action.SupportAttackers...),
	}
	if action.ResponseAttack != nil {
		response, err := decodeResponseAttack(*action.ResponseAttack)
		if err != nil {
			return engagement.Decision{}, err
		}
		out.Response = &response
	}
	if action.MoveTo != nil {
		cell := *action.MoveTo
		out.MoveTo = &cell
	}
	if action.Aim != nil {
		aim := *action.Aim
		out.Aim = &aim
	}
	return out, nil
}

func decodeResponseAttack(wire battle.ResponseAttack) (engagement.Response, error) {
	stance, known := decodedStances[wire.Stance]
	if !known {
		return engagement.Response{}, fmt.Errorf("%w: the response attack carries the stance %q",
			battle.ErrOutsideContract, wire.Stance)
	}
	return engagement.Response{
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

func encodeCells(cells []battle.Cell) []battle.Cell {
	return append(make([]battle.Cell, 0, len(cells)), cells...)
}

func encodeActions(unit *battle.Unit, moveCells []battle.Cell) battle.ActionsResponse {
	return battle.ActionsResponse{
		Unit:      encodeUnitStatus(unit),
		MoveCells: encodeCells(moveCells),
		Weapons:   encodeWeapons(unit),
		Skills:    encodeSkills(unit.Skills),
	}
}

func encodeUnitStatus(unit *battle.Unit) battle.UnitStatus {
	return battle.UnitStatus{
		UnitID:    unit.ID,
		Faction:   unit.Faction,
		Pos:       unit.Pos,
		Size:      unit.Footprint().Size,
		HP:        unit.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.EN,
		ENMax:     unit.ENMax,
		MoveRange: unit.Mech.MoveRange,
		Acted:     unit.Acted,
	}
}

func encodeWeapons(unit *battle.Unit) []battle.WeaponEntry {
	out := make([]battle.WeaponEntry, 0, len(unit.Mech.Weapons))
	for _, weapon := range unit.Mech.Weapons {
		out = append(out, battle.WeaponEntry{
			Name:            weapon.Name,
			RangeMin:        weapon.RangeMin,
			RangeMax:        weapon.RangeMax,
			ENCost:          weapon.ENCost,
			Ammo:            encodeAmmo(unit.Ammo, weapon.Name),
			Accuracy:        weapon.Accuracy,
			MapWeapon:       weapon.MapWeapon,
			UsableAfterMove: weapon.UsableAfterMove,
		})
	}
	return out
}

func encodeSkills(skills []battle.Skill) []battle.SkillEntry {
	out := make([]battle.SkillEntry, 0, len(skills))
	for _, skill := range skills {
		out = append(out, battle.SkillEntry{
			Kind:            skill.Kind,
			Amount:          battle.CloneAmount(skill.Amount),
			Uses:            skill.Uses,
			EndsActivation:  skill.EndsActivation,
			UsableAfterMove: skill.UsableAfterMove,
			RangeMin:        skill.RangeMin,
			RangeMax:        skill.RangeMax,
			Blast:           skill.Blast,
			Affects:         skill.Affects,
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

func encodeOptions(options engagement.Options) battle.ResponseAttacksResponse {
	return battle.ResponseAttacksResponse{
		Defender: battle.DefenderOptions{
			UnitID:           options.Defender.Unit.ID,
			ResponseAttacks:  encodeResponseAttackOptions(options.ResponseAttacks),
			SupportDefenders: encodeSupportDefenders(options.Defender.SupportDefenders),
			SupportAttackers: encodeSupportAttackers(options.Defender.SupportAttackers),
		},
		Attacker: battle.AttackerOptions{
			UnitID:           options.Attacker.Unit.ID,
			SupportDefenders: encodeSupportDefenders(options.Attacker.SupportDefenders),
			SupportAttackers: encodeSupportAttackers(options.Attacker.SupportAttackers),
		},
	}
}

func encodeResponseAttackOptions(options []engagement.ResponseAttackOption) []battle.ResponseAttackOption {
	out := make([]battle.ResponseAttackOption, 0, len(options))
	for _, option := range options {
		entry := battle.ResponseAttackOption{
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
func encodeForecast(forecast engagement.Forecast) battle.Forecast {
	out := battle.Forecast{HitRate: forecast.HitRate, Kill: forecast.Kill}
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

func encodeSupportDefenders(options []engagement.SupportDefendOption) []battle.SupportDefendOption {
	out := make([]battle.SupportDefendOption, 0, len(options))
	for _, option := range options {
		out = append(out, battle.SupportDefendOption{
			UnitID:   option.Unit.ID,
			Incoming: encodeForecast(option.Incoming),
		})
	}
	return out
}

func encodeSupportAttackers(options []engagement.SupportAttackOption) []battle.SupportAttackOption {
	out := make([]battle.SupportAttackOption, 0, len(options))
	for _, option := range options {
		out = append(out, battle.SupportAttackOption{
			UnitID: option.Unit.ID,
			Weapon: option.Weapon.Name,
			Strike: encodeForecast(option.Strike),
		})
	}
	return out
}

func encodeOptionalName(name string) *string {
	if name == "" {
		return nil
	}
	return &name
}
