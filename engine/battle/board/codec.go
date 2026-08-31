package board

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func encodeUnitStatus(unit *state.Unit) battle.UnitStatus {
	return battle.UnitStatus{
		UnitID:    unit.ID,
		Faction:   unit.Faction,
		Pos:       unit.Value.Pos,
		Size:      unit.Footprint().Size,
		HP:        unit.Value.HP,
		MaxHP:     unit.MaxHP,
		EN:        unit.Value.EN,
		ENMax:     unit.ENMax,
		MoveRange: unit.Mech.MoveRange,
		Acted:     unit.Value.Acted,
	}
}

func encodeWeapons(unit *state.Unit) []battle.WeaponEntry {
	out := make([]battle.WeaponEntry, 0, len(unit.Mech.Weapons))
	for _, weapon := range unit.Mech.Weapons {
		out = append(out, battle.WeaponEntry{
			Name:            weapon.Name,
			RangeMin:        weapon.RangeMin,
			RangeMax:        weapon.RangeMax,
			ENCost:          weapon.ENCost,
			Accuracy:        weapon.Accuracy,
			UsableAfterMove: weapon.UsableAfterMove,
		})
	}
	return out
}

func encodeMapWeapons(unit *state.Unit) []battle.MapWeaponEntry {
	out := make([]battle.MapWeaponEntry, 0, len(unit.Mech.MapWeapons))
	for _, weapon := range unit.Mech.MapWeapons {
		out = append(out, battle.MapWeaponEntry{
			Name:            weapon.Name,
			ApplyShape:      cloneShape(weapon.ApplyShape),
			EffectShape:     cloneShape(weapon.EffectShape),
			ENCost:          weapon.ENCost,
			Ammo:            encodeAmmo(unit.Value.Ammo, weapon.Name),
			Accuracy:        weapon.Accuracy,
			Affects:         weapon.Affects,
			UsableAfterMove: weapon.UsableAfterMove,
		})
	}
	return out
}

func encodeSkills(skills []def.Skill) []battle.SkillEntry {
	out := make([]battle.SkillEntry, 0, len(skills))
	for _, skill := range skills {
		out = append(out, battle.SkillEntry{
			Kind:            skill.Kind,
			Amount:          battle.CloneAmount(skill.Amount),
			Uses:            skill.Uses,
			EndsActivation:  skill.EndsActivation,
			UsableAfterMove: skill.UsableAfterMove,
			ApplyShape:      cloneShape(skill.ApplyShape),
			EffectShape:     cloneShape(skill.EffectShape),
			Affects:         skill.Affects,
		})
	}
	return out
}

func cloneShape(shape def.ShapeRange) battle.ShapeRange {
	return battle.ShapeRange{Cells: slices.Clone(shape.Cells), Direction: shape.Direction}
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
			Stance:   option.Stance,
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
