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
	weaponID string) ([]Reaction, error) {
	defender, err := b.livingUnit(defenderID)
	if err != nil {
		return nil, err
	}
	attacker, err := b.livingUnit(attackerID)
	if err != nil {
		return nil, err
	}
	weapon := attacker.Weapon(weaponID)
	if weapon == nil {
		return nil, fmt.Errorf("unit %q carries no weapon %q", attackerID, weaponID)
	}
	// A map strike permits no reaction, and the blast reaches a unit outside the
	// band of the weapon, so the empty list comes before the band check.
	if weapon.MapWeapon {
		return []Reaction{}, nil
	}
	origin := footprintAt(attacker, attackerCell)
	distance := SpanDistance(defender.Footprint, origin)
	if !weapon.Range.Holds(distance) {
		return nil, fmt.Errorf("the weapon %q of unit %q does not reach unit %q from %v",
			weaponID, attackerID, defenderID, attackerCell)
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
		if counterFits(defender, counter, distance) {
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
	if b.hasSupportAttacker(defender, defender.Footprint, origin) {
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

// SupportDefender gives the interceptor of a strike on the defender. The game
// picks one interceptor for each engagement (docs/reference/combat-formulas.md,
// case 16), so the first eligible unit is the answer.
func (b *Board) SupportDefender(defender *Unit) *Unit {
	for _, other := range b.ByFaction(defender.Faction) {
		if inSupportReach(other, defender, defender.Footprint, other.SupportDefendCharges) {
			return other
		}
	}
	return nil
}

// AttackShieldBearer gives the unit that takes a counter strike for the
// attacker, or nil. The bearer intercepts on the attack of its own side
// (docs/reference/combat-formulas.md, case 6, issue #22).
func (b *Board) AttackShieldBearer(attacker *Unit) *Unit {
	for _, other := range b.ByFaction(attacker.Faction) {
		if other.AttackShield &&
			inSupportReach(other, attacker, attacker.Footprint, other.SupportDefendCharges) {
			return other
		}
	}
	return nil
}

// SupportAttackers gives the units that can join a strike of the supported unit
// against a foe on 'foe', each one with the weapon it fires. The supported unit
// fires from 'firing', which is its anchor after its move.
func (b *Board) SupportAttackers(supported *Unit, firing, foe Footprint) []SupportAttacker {
	var out []SupportAttacker
	for _, other := range b.ByFaction(supported.Faction) {
		if weapon := supportWeapon(other, supported, firing, foe); weapon != nil {
			out = append(out, SupportAttacker{Unit: other, Weapon: weapon})
		}
	}
	return out
}

func (b *Board) hasSupportAttacker(supported *Unit, firing, foe Footprint) bool {
	for _, other := range b.ByFaction(supported.Faction) {
		if supportWeapon(other, supported, firing, foe) != nil {
			return true
		}
	}
	return false
}

func supportWeapon(other, supported *Unit, firing, foe Footprint) *Weapon {
	if !inSupportReach(other, supported, firing, other.SupportAttackCharges) {
		return nil
	}
	distance := SpanDistance(other.Footprint, foe)
	for index := range other.Weapons {
		weapon := &other.Weapons[index]
		if !weapon.MapWeapon && other.HasENFor(*weapon) && weapon.Range.Holds(distance) {
			return weapon
		}
	}
	return nil
}

// The support reach of a unit is the move range of that unit
// (docs/reference/combat-formulas.md, case 14).
func inSupportReach(other, supported *Unit, at Footprint, charges int) bool {
	return other.ID != supported.ID && charges > 0 &&
		SpanDistance(other.Footprint, at) <= other.MoveRange
}
