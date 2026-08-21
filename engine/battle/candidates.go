package battle

// Actions gives the legal actions of one unit: the attacks, the map attacks,
// the skills, the repositions and the standby, in that order.
func (b *Board) Actions(unitID string) ([]Decision, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return nil, err
	}
	targets := b.TargetsOf(unit)
	anchors := cellSlice(ReachableAnchors(unit.Footprint, unit.MoveRange,
		b.BlockingCells(unit), b.OccupiedCells(unit), b.Bounds))

	out := attacks(unit, targets, anchors)
	out = append(out, mapAttacks(unit, targets, anchors)...)
	out = append(out, skillActions(unit)...)
	out = append(out, repositions(unit, targets, anchors)...)
	return append(out, Decision{UnitID: unit.ID, Kind: ActionStandby, Support: true}), nil
}

func attacks(unit *Unit, targets []*Unit, anchors []Cell) []Decision {
	var out []Decision
	for _, target := range targets {
		for index := range unit.Weapons {
			weapon := &unit.Weapons[index]
			if weapon.MapWeapon || !unit.HasENFor(*weapon) {
				continue
			}
			destination, found := firingAnchor(unit, weapon, target.Footprint, anchors)
			if !found {
				continue
			}
			out = append(out, Decision{
				UnitID:   unit.ID,
				Kind:     ActionAttack,
				MoveTo:   move(unit, destination),
				TargetID: target.ID,
				Weapon:   weapon.Name,
				Support:  true,
			})
		}
	}
	return out
}

// A map attack names its area center in 'aim' and no target, because the strike
// hits every unit of the blast.
func mapAttacks(unit *Unit, targets []*Unit, anchors []Cell) []Decision {
	var out []Decision
	for index := range unit.Weapons {
		weapon := &unit.Weapons[index]
		if !weapon.MapWeapon || unit.Ammo[weapon.Name] <= 0 || !unit.HasENFor(*weapon) {
			continue
		}
		for _, target := range targets {
			destination, found := firingAnchor(unit, weapon, target.Footprint, anchors)
			if !found {
				continue
			}
			aim := aimCell(footprintAt(unit, destination), target.Footprint)
			out = append(out, Decision{
				UnitID:  unit.ID,
				Kind:    ActionMapAttack,
				MoveTo:  move(unit, destination),
				Weapon:  weapon.Name,
				Aim:     &aim,
				Support: true,
			})
		}
	}
	return out
}

// The enumeration keeps the skill whose area is the cell of the caster: a
// range of 0 and a blast of 0. A skill of a wider area names the center of that
// area in 'aim', and no rule picks that center.
func skillActions(unit *Unit) []Decision {
	var out []Decision
	for _, skill := range unit.Skills {
		if skill.Uses <= 0 || skill.Range.Max != 0 || skill.Blast != 0 ||
			!skillHasRoom(unit, skill) {
			continue
		}
		out = append(out, Decision{
			UnitID:  unit.ID,
			Kind:    skill.Kind,
			Amount:  cloneAmount(skill.Amount),
			Support: true,
		})
	}
	return out
}

func skillHasRoom(unit *Unit, skill Skill) bool {
	switch skill.Kind {
	case ActionSkillHeal:
		return unit.HP < unit.MaxHP
	case ActionSkillRefill:
		return unit.EN < unit.ENMax
	default:
		return false
	}
}

// A reposition keeps a step forward and a step back in the candidate list.
func repositions(unit *Unit, targets []*Unit, anchors []Cell) []Decision {
	if unit.MoveRange <= 0 || len(targets) == 0 {
		return nil
	}
	picks := make([]Cell, 0, len(targets)+1)
	for _, target := range targets {
		picks = append(picks, pickAnchor(unit, anchors, target.Footprint, nearness.before))
	}
	picks = append(picks, pickAnchor(unit, anchors, nearestTarget(unit, targets).Footprint,
		func(key, best nearness) bool { return best.before(key) }))

	var out []Decision
	taken := CellSet{unit.Footprint.Anchor: true}
	for _, cell := range picks {
		if taken[cell] {
			continue
		}
		taken[cell] = true
		destination := cell
		out = append(out, Decision{
			UnitID:  unit.ID,
			Kind:    ActionReposition,
			MoveTo:  &destination,
			Support: true,
		})
	}
	return out
}

func nearestTarget(unit *Unit, targets []*Unit) *Unit {
	nearest := targets[0]
	best := SpanDistance(unit.Footprint, nearest.Footprint)
	for _, target := range targets[1:] {
		if distance := SpanDistance(unit.Footprint, target.Footprint); distance < best {
			nearest, best = target, distance
		}
	}
	return nearest
}

// firingAnchor keeps one destination per pair of a target and a weapon, so the
// branching factor of the search stays with the weapons and not with the
// anchors of the board.
func firingAnchor(unit *Unit, weapon *Weapon, target Footprint, anchors []Cell) (Cell, bool) {
	var best Cell
	var bestKey nearness
	found := false
	for _, cell := range firingAnchors(unit, weapon, anchors) {
		if !weapon.Range.Holds(SpanDistance(footprintAt(unit, cell), target)) {
			continue
		}
		key := nearnessOf(unit, cell, unit.Footprint)
		if !found || key.before(bestKey) {
			best, bestKey, found = cell, key, true
		}
	}
	return best, found
}

func firingAnchors(unit *Unit, weapon *Weapon, anchors []Cell) []Cell {
	if weapon.UsableAfterMove {
		return anchors
	}
	return []Cell{unit.Footprint.Anchor}
}

func pickAnchor(unit *Unit, anchors []Cell, other Footprint,
	better func(key, best nearness) bool) Cell {
	best, bestKey := anchors[0], nearnessOf(unit, anchors[0], other)
	for _, cell := range anchors[1:] {
		if key := nearnessOf(unit, cell, other); better(key, bestKey) {
			best, bestKey = cell, key
		}
	}
	return best
}

// nearness ranks the anchors of one unit against one footprint. The distance of
// the board comes first. Two anchors at that distance part on the squared
// Euclid distance of the two anchors, which prefers the straight line, and then
// on the coordinate, which makes the pick deterministic.
type nearness struct {
	distance int
	euclid   int
	cell     Cell
}

func nearnessOf(unit *Unit, cell Cell, other Footprint) nearness {
	dx := cell[0] - other.Anchor[0]
	dy := cell[1] - other.Anchor[1]
	return nearness{
		distance: SpanDistance(footprintAt(unit, cell), other),
		euclid:   dx*dx + dy*dy,
		cell:     cell,
	}
}

func (n nearness) before(other nearness) bool {
	if n.distance != other.distance {
		return n.distance < other.distance
	}
	if n.euclid != other.euclid {
		return n.euclid < other.euclid
	}
	return n.cell.Before(other.cell)
}

// aimCell keeps the aim of a map attack inside the band that the enumeration
// checked: the band holds the distance between the two footprints, and that
// distance is the distance to the cell of the target nearest to the shooter.
func aimCell(firing, target Footprint) Cell {
	cells := target.Cells()
	best, bestDistance := cells[0], SpanDistance(cellFootprint(cells[0]), firing)
	for _, cell := range cells[1:] {
		if distance := SpanDistance(cellFootprint(cell), firing); distance < bestDistance {
			best, bestDistance = cell, distance
		}
	}
	return best
}

func cellFootprint(cell Cell) Footprint {
	return Footprint{Anchor: cell, Size: Size{1, 1}}
}

func footprintAt(unit *Unit, anchor Cell) Footprint {
	return Footprint{Anchor: anchor, Size: unit.Footprint.Size}
}

func move(unit *Unit, destination Cell) *Cell {
	if destination == unit.Footprint.Anchor {
		return nil
	}
	return &destination
}
