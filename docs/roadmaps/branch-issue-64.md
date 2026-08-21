# Branch roadmap: issue 64, the engagement resolution

> Type: working—deleted at merge

## Where the branch stands

The branch stands on 'issue-63-candidates' (40b7e3a), which
stands on 'issue-62-formulas' (5e25add). Merge #62, #63, then
this branch, in order.

## Change summary

The engine applies one decision to the board: the move, the
engagement in the order of docs/reference/combat-formulas.md, the
map attack, the skill, and the activation bookkeeping. Python is
the oracle for the resulting state only; the Go code is designed
from the domain.

New:

- 'engine/battle/resolve.go': 'Board.Apply(decision, dice)
  (Trace, error)'. It gates the actor through 'Activatable',
  validates the whole action before it writes anything (a foe
  target, a paid weapon, the band from the final anchor, a legal
  move, a reaction that 'Reactions' gives), then resolves. One
  'volley' value carries the struck unit, the multiplier and the
  interceptor; every landed hit of the attacker volley and the
  main strike goes to that unit, and the interceptor spends one
  charge on the first landed hit. The defender volley and the
  counter follow when the defender lives and the reaction says
  so; the counter may land on the attack shield bearer. A map
  attack spends ammo and EN and damages every foe inside the
  blast of the aim. A skill spends a use and heals or refills the
  caster. A kill with a chance step left gives the re-act. The
  'Trace' is the list of strike records.
- 'engine/battle/dice.go': the chance nodes 'NodeSupportVolley',
  'NodeStrike', 'NodeDefenderVolley', 'NodeCounter'; the 'Dice'
  interface 'Lands(node, probability)'; 'Forced' with one outcome
  per node. The sampled dice is #65.
- 'engine/battle/strike.go': 'StrikeDamage' (rounded half to even,
  as the oracle), 'StrikeHitProbability' (the dodge penalty of the
  rules), 'Rules.StanceMultiplier', 'Rules.InterceptionMultiplier',
  'Board.CounterWeapon', 'Board.AttackShieldBearer'.
- 'engine/battle/model.go', 'codec.go': 'Rules' with
  'DefaultRules' and 'DecodeRules' (every field validated; a
  payload that carries the rules carries every field); the unit
  fields of the engagement ('ChanceSteps' and its maximum, the two
  charge maxima, 'AttackShield', 'InterceptionReduction',
  'Debuffs'); the weapon fields 'Power', 'Accuracy', 'Blast', the
  debuff it applies; 'Skill.Source'; 'Decision.Reaction';
  'DecodeDecision', 'DecodeReaction', 'EncodeUnit', 'EncodeUnits';
  'PhaseOrder', 'Board.PhaseIndex'; 'NewBoard' takes the rules.
- 'engine/differential/resolve_test.go': the op 'apply'; three
  boards, 25 checks, every one matching the oracle.
- Hand-written Go tests: 'resolve_test.go', 'strike_test.go', and
  additions to 'candidates_test.go' and 'codec_test.go'.

Changed:

- 'Board.Actions' gives an attack with 'Support' true and false
  when a support attacker of the actor qualifies from the firing
  anchor and the rules cap is above zero; every other action
  carries 'Support' false. 'SupportAttackers' takes the firing
  footprint. The spec section 'actions' says so.
- 'docs/reference/terminology-map.md': the row 'support volley';
  the spec and the comments use 'volley' for the shots and
  'support attack' for the choice.
- 'scripts/write_engine_fixtures.py', 'tests/test_engine_codec.py':
  the three boards, the 'support' normalization of the #63
  'actions' expectations, the dice object, the coverage tests.

## Exported Go API

    type Rules; func DefaultRules() Rules
    func DecodeRules(*protocol.Rules) (Rules, error)
    func (r Rules) StanceMultiplier(Stance) float64
    func (r Rules) InterceptionMultiplier(*Unit) float64
    var PhaseOrder; func (b *Board) PhaseIndex() int
    func StrikeDamage(attacker, defender *Unit, weapon *Weapon,
        defense float64, rules Rules) int
    func StrikeHitProbability(attacker, defender *Unit,
        weapon *Weapon, dodging bool, rules Rules) float64
    func (b *Board) CounterWeapon(defender *Unit, name string,
        attacker Footprint) *Weapon
    func (b *Board) AttackShieldBearer(attacker *Unit) *Unit
    func (b *Board) SupportAttackers(supported *Unit,
        firing, foe Footprint) []SupportAttacker
    type Node; type Dice interface; type Forced struct
    type Strike; type Trace []Strike
    func (b *Board) Apply(decision Decision, dice Dice) (Trace, error)
    var ErrIllegalAction, ErrIllegalMove error

## Call chain

The differential op decodes the board with the rules of the
setup, decodes the decision, applies it with 'Forced', and
answers the living units in board order. No server command calls
'Apply' yet: 'act' is #65, which also wires the two sentinel
errors to 'illegal_action'.

## Rules that diverge from the Python oracle

On top of the four of #63:

5. The attacker chooses the support attack ('Decision.Support');
   Python fires every supporter on every attack. The writer
   normalizes the 'support' field of the #63 'actions'
   expectations to this rule.
6. The attacker volley and the defender volley are two chance
   nodes; Python settles both with one field. The fixtures give
   both nodes the same outcome.
7. An illegal move, a non-foe target, a reaction that 'Reactions'
   does not give, a skill target other than the caster: errors.
   Python ignores or falls back in silence.
8. A destroyed unit stays on the board with HP 0; Python removes
   it. Both sides filter on life before the compare.

Not in this branch: the critical hit (no source holds a rate;
#48), the phase rotation, the EN regeneration, the debuff expiry,
the stage events, the sampled dice, the 'act' command (#65).

## Contention points

1. 'Apply' validates the reaction against the enumeration, so a
   reaction with 'support_attack' false on a board with no
   defender supporter is refused (the enumeration gives the false
   variant only when a supporter exists). The contract promises
   illegal_action for a reaction that 'reactions' does not give;
   the strict reading stands. One line in 'legalReaction' relaxes
   it if the user prefers.
2. The hit probability of the main strike reads the target with
   its dodge penalty, not the interceptor, as the oracle does.
   Whose evasion the game reads when an interceptor takes the
   strike is not measured; the oracle value stands until it is.
   Under 'Forced' nothing reads the probability.
3. One die settles a whole volley, with the probability of the
   first shot; a die per supporter is #47. #65 must not land a
   sampler before #47 settles the per-supporter roll.
4. The rules enter the board through 'NewBoard'; 'DecodeState'
   installs the defaults and the differential op overrides them
   from the setup. 'load' carries no rules on the wire; the
   session rules come with 'init' (#65 or the deploy issue).
5. A skill decision addresses the first skill of its kind with a
   use left and an equal amount; two identical skills are
   indistinguishable on the wire.
6. HP clamps at 0.

## Verification

- From 'engine': go vet clean; go test ok (battle, differential,
  protocol, server); gofmt clean.
- uv run ruff check src tests scripts: all checks passed.
- uv run pytest -q: 1128 passed, 4 skipped.
- uv run python scripts/write_engine_fixtures.py --check: clean.
- 25 'apply' checks on 'engagement_board', 'kill_skill_board',
  'attack_shield_board', every one matching the oracle; a
  one-point damage change fails 7 checks.
- Code review (2026-08-21, high effort): 19 verified items; the
  correctness and cleanup items are applied in 384dcbd and
  96a1ba9. Declined: hoisting the support check per target and
  the 'ByFaction' allocation pass (the advisor issue profiles
  first), a rules path through 'load' (point 4), the
  'ENRegenFraction' reader (#65).

## Open points

- 'Board.Roster' still panics; it belongs to the deploy flow.
- The per-supporter hit roll (#47) and the critical roll (#48)
  change the chance nodes of 'Apply'.
