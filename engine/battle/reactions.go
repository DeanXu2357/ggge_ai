package battle

import "fmt"

// SupportAttacker is one unit that joins the strike of the unit it supports,
// with the first weapon of that unit that reaches the foe.
type SupportAttacker struct {
	Unit   *Unit
	Weapon *Weapon
}

// Reactions gives the legal reactions of one defender against one planned
// strike. The strike comes from 'attackerCell', not from the cell of the
// attacker today: the client asks about a move that did not occur.
func (b *Board) Reactions(defenderID, attackerID string, attackerCell Cell,
	weaponName string) ([]Reaction, error) {
	defender := b.Unit(defenderID)
	if defender == nil {
		return nil, fmt.Errorf("the board holds no unit %q", defenderID)
	}
	attacker := b.Unit(attackerID)
	if attacker == nil {
		return nil, fmt.Errorf("the board holds no unit %q", attackerID)
	}
	weapon := attacker.Weapon(weaponName)
	if weapon == nil {
		return nil, fmt.Errorf("unit %q carries no weapon %q", attackerID, weaponName)
	}
	origin := footprintAt(attacker, attackerCell)
	distance := SpanDistance(defender.Footprint, origin)
	if !weapon.Range.Holds(distance) {
		return nil, fmt.Errorf("the weapon %q of unit %q does not reach unit %q from %v",
			weaponName, attackerID, defenderID, attackerCell)
	}
	if weapon.MapWeapon {
		return []Reaction{}, nil
	}

	out := []Reaction{
		{Stance: StanceDodge, SupportAttack: true},
		{Stance: StanceDefend, SupportAttack: true},
	}
	if defender.HasShield {
		out = append(out, Reaction{Stance: StanceShield, SupportAttack: true})
	}
	for index := range defender.Weapons {
		counter := &defender.Weapons[index]
		if counter.MapWeapon || !counter.CanCounter || defender.EN < counter.ENCost {
			continue
		}
		if counter.Range.Holds(distance) {
			out = append(out, Reaction{
				Stance:        StanceCounter,
				Weapon:        counter.Name,
				SupportAttack: true,
			})
		}
	}
	if b.SupportDefender(defender) != nil {
		out = append(out, supportDefendVariants(out)...)
	}
	if len(b.SupportAttackers(defender, origin)) > 0 {
		out = append(out, supportAttackVariants(out)...)
	}
	return out, nil
}

// A defender that picks defend or shield blocks the strike for itself and
// leaves the interceptor nothing to take, so support defense pairs with dodge
// and with counter alone (docs/reference/battle-prep-ui.md, issue #44).
func supportDefendVariants(options []Reaction) []Reaction {
	var out []Reaction
	for _, option := range options {
		if option.Stance != StanceDodge && option.Stance != StanceCounter {
			continue
		}
		option.SupportDefend = true
		out = append(out, option)
	}
	return out
}

func supportAttackVariants(options []Reaction) []Reaction {
	out := make([]Reaction, 0, len(options))
	for _, option := range options {
		option.SupportAttack = false
		out = append(out, option)
	}
	return out
}

// SupportDefender gives the first unit that can intercept a strike on the
// defender: one unit of its faction, alive, with a charge left, that stands
// within its own move range of the defender.
func (b *Board) SupportDefender(defender *Unit) *Unit {
	for index := range b.Units {
		other := &b.Units[index]
		if other.ID == defender.ID || !other.Alive() || other.Faction != defender.Faction {
			continue
		}
		if other.SupportDefendCharges <= 0 {
			continue
		}
		if SpanDistance(other.Footprint, defender.Footprint) <= other.MoveRange {
			return other
		}
	}
	return nil
}

// SupportAttackers gives the units that can join a strike of the supported unit
// against a foe on 'foe': one unit of its faction, alive, with a charge left,
// within its own move range of the supported unit, that carries a weapon it can
// pay for and that reaches the foe.
func (b *Board) SupportAttackers(supported *Unit, foe Footprint) []SupportAttacker {
	var out []SupportAttacker
	for index := range b.Units {
		other := &b.Units[index]
		if other.ID == supported.ID || !other.Alive() || other.Faction != supported.Faction {
			continue
		}
		if other.SupportAttackCharges <= 0 {
			continue
		}
		if SpanDistance(other.Footprint, supported.Footprint) > other.MoveRange {
			continue
		}
		distance := SpanDistance(other.Footprint, foe)
		for weaponIndex := range other.Weapons {
			weapon := &other.Weapons[weaponIndex]
			if weapon.MapWeapon || other.EN < weapon.ENCost || !weapon.Range.Holds(distance) {
				continue
			}
			out = append(out, SupportAttacker{Unit: other, Weapon: weapon})
			break
		}
	}
	return out
}
