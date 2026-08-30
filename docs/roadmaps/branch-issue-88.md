# Branch roadmap: issue 88, the battle engine as definitions, state and systems

> Type: working—deleted at merge

Issue: #88. Branch: issue-88-engine-restructure. Status: in-progress.
Base: dev c65f416. The #72 branch (issue-72-mech-pilot-unit, head
9cad225) is the source of parts for #72 after this branch merges.

## Design (approved before code)

Three kinds of package below the contract 'engine/battle', and one
shell. Imports run one way: shell -> systems -> state -> def ->
formula. A system never imports another system except through the
pure ones (geometry).

### Static definitions: 'engine/battle/def'

Immutable after decode. Exported fields. Shared by pointer between
every clone of a board.

    type Mech struct {
        HP, EN                      int
        Attack, Defense, Mobility   float64
        MoveRange                   int
        Weapons                     []Weapon
    }
    type Pilot struct {
        Ranged, Melee, Awaken, Defense, Reaction float64
        SP                                      int
    }
    type Weapon struct {
        Name            string
        Power           float64
        Range           RadiusRange
        ENCost          int
        Accuracy        float64
        MapWeapon       bool
        UsableAfterMove bool
        DebuffKind      string
        DebuffMagnitude float64
        Categories      []WeaponCategory
    }
    type RadiusRange struct{ Min, Max int }   // Holds(distance int) bool
    type WeaponCategory string                // ranged, melee, awaken

No 'CanCounter': a counter fires under the rule of an attack (user
ruling 2026-08-30). The ability fields of #72 land here later.

### Dynamic state: 'engine/battle/state'

Small structs, exported fields, no methods that decide anything.
'Board.Clone' copies the units and their slices and maps; the
definitions stay shared.

    type Unit struct {
        ID        string
        Faction   Faction
        Footprint Footprint
        Mech      *def.Mech
        Pilot     *def.Pilot
        HP, MaxHP, EN, ENMax, SP, SPMax int
        Acted     bool
        ChanceSteps, ChanceStepsMax                     int
        SupportDefendCharges, SupportDefendChargesMax   int
        SupportAttackCharges, SupportAttackChargesMax   int
        HasShield, SupportDefendWhenAttack              bool
        Ammo      map[string]int
        Debuffs   []Debuff
        Skills    []Skill        // per-unit wire data; no rule reads it (#81)
    }
    type Board struct {
        Bounds         Bounds
        Units          []Unit
        Phase          Faction
        Turn           int
        DefaultTerrain Terrain
        TerrainCells   map[Cell]Terrain
    }
    // Vocabulary of the grid: Cell, Size, Footprint, Bounds, Faction,
    // Terrain, Debuff, Skill and the skill enums.
    func (b *Board) Unit(id string) *Unit      // lookup, nil when absent
    func (b *Board) Clone() Board

### Pure systems (read, never write)

'engine/battle/geometry':

    func Distance(a, b state.Footprint) int
    func FootprintAt(unit *state.Unit, anchor state.Cell) state.Footprint
    func Within(f state.Footprint, bounds state.Bounds) bool
    func Occupied(board *state.Board, except string) CellSet
    func Blocking(board *state.Board, unit *state.Unit) CellSet
    func ReachableAnchors(board *state.Board, unit *state.Unit) CellSet
    func SortedCells(set CellSet) []state.Cell

'engine/battle/abilities' arrives with #72 (condition sums, scaled
stats); in this issue the maxima come from the definitions alone.

### Writing systems

'engine/battle/engagement' — one activation of one unit: the move,
the exchange, the end of the activation.

    type Decision struct {          // the domain form of protocol.Decision
        UnitID   string
        Kind     ActionKind         // attack, map_attack, reposition, standby
        MoveTo   *state.Cell
        TargetID string
        Weapon   string
        SupportDefender  string
        SupportAttackers []string
        Response *Response
    }
    type Response struct {
        Stance           Stance
        Weapon           string
        SupportDefender  string
        SupportAttackers []string
    }

    // Prepare validates every participant and writes nothing. Every
    // error of 'Act' comes from here: battle.ErrNoUnit, ErrDestroyed,
    // ErrOffPhase, ErrActed, ErrIllegalMove, ErrIllegalAction.
    func Prepare(board *state.Board, decision Decision) (Plan, error)

    // Plan is the ordered list of steps with every choice resolved:
    // the anchor, the target, the weapon, each supporter with its
    // weapon and distance, the bearer, the stance, the counter weapon.
    type Plan struct { ... unexported ... }

    // Commit writes the plan in order and cannot fail. It stops when
    // the receiver of the next strike is destroyed; a shooter that
    // died earlier in the exchange is skipped.
    func Commit(board *state.Board, plan Plan, dice battle.Dice) Trace

    // Menu answers 'response_attacks' with the same eligibility
    // helpers Prepare uses, so the menu and the check never diverge.
    func Menu(board *state.Board, decision Decision, defenderID string) (Menu, error)

    type Trace []Strike; type Strike struct {Kind, ShooterID, StruckID,
    Weapon, Landed, Damage, Killed}; type Forecast; type Menu with the
    option types of today (results.go).

  Prepare, in order: the actor (exists, alive, of the phase, not
  acted); the kind (map_attack refused); the anchor (nil = stay;
  reachable; permitted after the move for the weapon); for an attack:
  the target (exists, alive, opposing), the weapon (exists, not a map
  weapon), the reach from the firing footprint, the EN; the bearer
  (named: same faction, alive, covers when attacking, a defend charge,
  within its move range of the firing footprint); the response
  (stance known; a counter weapon that is not a map weapon, reaches
  the firing footprint, the EN; a support defender: same faction,
  alive, a defend charge, within its move range of the defender, not
  with the defend stance; support attackers: at most three, unique,
  same faction, alive, an attack charge, within move range of the
  defender, a weapon that reaches the firing footprint with the EN;
  their 'other' for the EN is the attacker); the attacker's support
  attackers likewise against the target (their 'other' is the unit
  that takes the main strike).

  Commit, in order: the anchor; the actor's EN; the attacker's salvo
  (each supporter: charge, EN, one die for the salvo, strike); the
  main strike (the receiver is the defender's support defender when
  named — its charge — else the target with the stance multiplier;
  the hit rate reads the target); stop if the receiver is destroyed
  [golden check: engagement_board.json and kill_skill_board.json
  decide whether a salvo that kills the target still lets the main
  strike land on the corpse; if a golden contradicts the rule the
  user rules]; the defender's salvo (defender alive, attacker alive);
  the counter (attacker alive; the bearer covers when it holds a
  charge — its charge; the EN of the counter is spent on a miss as
  well); the end of the activation (a kill with a chance step left
  spends the step and keeps the unit active, else acted).

'engine/battle/turn':

    func Advance(board *state.Board) []Rotation     // phase rotation,
        // EN regeneration, debuff expiry, acted reset, as turn.go today

'engine/battle/deploy':

    func Assemble(unit *state.Unit)   // maxima from the definitions
        // (fillMaxima today); #72 adds the abilities
    // 'Place' comes with #72.

### The shell: 'engine/battle/board'

    type Board struct{ state state.Board }   // implements battle.Board
    DecodeInit, DecodeState                  // wire -> def + state
    Act: decode -> engagement.Prepare -> engagement.Commit ->
         turn.Advance -> encode. Atomic by construction: Prepare
         returns before the first write and Commit cannot fail, so
         handler/act.go drops its clone.
    Capabilities, ReachableCells: geometry
    ResponseAttacks: engagement.Menu
    Clone: state.Board.Clone
    State, Summary: encode

The codec (wire <-> def/state) stays in the shell in two files: one
for the definitions, one for the state. Every parse of a wire name
lives there.

### Rule of writes

Only 'engagement.Commit', 'turn.Advance', 'deploy.Assemble' and the
shell's decoders assign a field of 'state.Unit' or 'state.Board'.
Review check: grep for assignments to those fields outside the three
systems and the codec files.

### Stages (each with every gate green and the goldens byte-identical)

A. 'def', 'state', 'geometry' introduced; the existing board code
   rewired to them mechanically (the flow untouched).
B. 'engagement' (Prepare/Commit/Menu), 'turn', 'deploy' written from
   the design; the old resolve.go, strike.go, forecast.go,
   response_attacks.go, results.go deleted; the shell reduced.
C. 'can_counter' removed (protocol 1.5, Python mirror, fixtures,
   scenario placeholder); handler clone dropped.
D. Spec process model, terminology map, ledger, the artifact.

## Progress log

- 2026-08-30: the design above, for the user's approval before code.
