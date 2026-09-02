package engagement

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

type supportAttacker struct {
	UnitID   int
	WeaponID int
}

// The supported unit stands on 'at' after its move, so the reach of a
// support unit reads that cell and not the cell of today.
func supportDefenders(board state.Battle, supportedID int, at battle.Footprint) []int {
	out := []int{}
	supported, err := board.UnitAt(supportedID)
	if err != nil {
		return out
	}
	for _, otherID := range byFaction(board, supported.Faction) {
		other := unitOf(board, otherID)
		if inSupportReach(board, otherID, supportedID, at, other.Value.SupportDefendCharges) {
			out = append(out, otherID)
		}
	}
	return out
}

func supportAttackers(board state.Battle, supportedID int,
	firing, foe battle.Footprint) []supportAttacker {
	out := []supportAttacker{}
	supported, err := board.UnitAt(supportedID)
	if err != nil {
		return out
	}
	for _, otherID := range byFaction(board, supported.Faction) {
		if weaponID, joins := supportWeapon(board, otherID, supportedID, firing, foe); joins {
			out = append(out, supportAttacker{UnitID: otherID, WeaponID: weaponID})
		}
	}
	return out
}

func supportWeapon(board state.Battle, otherID, supportedID int,
	firing, foe battle.Footprint) (int, bool) {
	other, err := board.UnitAt(otherID)
	if err != nil {
		return 0, false
	}
	if !inSupportReach(board, otherID, supportedID, firing, other.Value.SupportAttackCharges) {
		return 0, false
	}
	distance := geometry.Distance(other.Footprint(), foe)
	for index := range other.Mech.Weapons {
		if fires(other, &other.Mech.Weapons[index], distance) {
			return index, true
		}
	}
	return 0, false
}

func inSupportReach(board state.Battle, otherID, supportedID int,
	at battle.Footprint, charges int) bool {
	if otherID == supportedID || charges <= 0 {
		return false
	}
	other, err := board.UnitAt(otherID)
	if err != nil {
		return false
	}
	return geometry.Distance(other.Footprint(), at) <= other.Mech.MoveRange
}
