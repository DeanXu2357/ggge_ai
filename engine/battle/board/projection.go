package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func unitStatusOf(unitID int, unit state.Unit) battle.UnitStatus {
	return battle.UnitStatus{
		UnitID:    unitID,
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

func weaponEntriesOf(unit state.Unit) []battle.WeaponEntry {
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

func mapWeaponEntriesOf(unit state.Unit) []battle.MapWeaponEntry {
	out := make([]battle.MapWeaponEntry, 0, len(unit.Mech.MapWeapons))
	for index, weapon := range unit.Mech.MapWeapons {
		out = append(out, battle.MapWeaponEntry{
			Name:            weapon.Name,
			ApplyShape:      state.ToContractShape(weapon.ApplyShape),
			EffectShape:     state.ToContractShape(weapon.EffectShape),
			ENCost:          weapon.ENCost,
			Ammo:            unit.Value.MapWeaponAmmo[index],
			Accuracy:        weapon.Accuracy,
			Affects:         weapon.Affects,
			UsableAfterMove: weapon.UsableAfterMove,
		})
	}
	return out
}

func skillEntriesOf(skills []def.Skill) []battle.SkillEntry {
	out := make([]battle.SkillEntry, 0, len(skills))
	for _, skill := range skills {
		out = append(out, battle.SkillEntry{
			Kind:            skill.Kind,
			Amount:          battle.CloneAmount(skill.Amount),
			Uses:            skill.Uses,
			EndsActivation:  skill.EndsActivation,
			UsableAfterMove: skill.UsableAfterMove,
			ApplyShape:      state.ToContractShape(skill.ApplyShape),
			EffectShape:     state.ToContractShape(skill.EffectShape),
			Affects:         skill.Affects,
		})
	}
	return out
}

func responseAttacksOf(options engagement.Options) battle.ResponseAttacksResponse {
	return battle.ResponseAttacksResponse{
		Defender: battle.DefenderOptions{
			UnitID:           options.Defender.UnitID,
			ResponseAttacks:  responseAttackOptionsOf(options.ResponseAttacks),
			SupportDefenders: supportDefendersOf(options.Defender.SupportDefenders),
			SupportAttackers: supportAttackersOf(options.Defender.SupportAttackers),
		},
		Attacker: battle.AttackerOptions{
			UnitID:           options.Attacker.UnitID,
			SupportDefenders: supportDefendersOf(options.Attacker.SupportDefenders),
			SupportAttackers: supportAttackersOf(options.Attacker.SupportAttackers),
		},
	}
}

func responseAttackOptionsOf(options []engagement.ResponseAttackOption) []battle.ResponseAttackOption {
	out := make([]battle.ResponseAttackOption, 0, len(options))
	for _, option := range options {
		entry := battle.ResponseAttackOption{
			Stance:   option.Stance,
			WeaponID: cloneID(option.WeaponID),
			Incoming: forecastOf(option.Incoming),
		}
		if option.Counter != nil {
			counter := forecastOf(*option.Counter)
			entry.Counter = &counter
		}
		out = append(out, entry)
	}
	return out
}

// The wire carries no integer type, so the damage goes out as a number.
func forecastOf(forecast engagement.Forecast) battle.Forecast {
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

func supportDefendersOf(options []engagement.SupportDefendOption) []battle.SupportDefendOption {
	out := make([]battle.SupportDefendOption, 0, len(options))
	for _, option := range options {
		out = append(out, battle.SupportDefendOption{
			UnitID:   option.UnitID,
			Incoming: forecastOf(option.Incoming),
		})
	}
	return out
}

func supportAttackersOf(options []engagement.SupportAttackOption) []battle.SupportAttackOption {
	out := make([]battle.SupportAttackOption, 0, len(options))
	for _, option := range options {
		out = append(out, battle.SupportAttackOption{
			UnitID:   option.UnitID,
			WeaponID: option.WeaponID,
			Strike:   forecastOf(option.Strike),
		})
	}
	return out
}

func cloneID(id *int) *int {
	if id == nil {
		return nil
	}
	out := *id
	return &out
}
