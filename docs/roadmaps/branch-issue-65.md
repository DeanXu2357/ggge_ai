# Branch roadmap: issue 65, the turn cycle and the act command

> Type: working—deleted at merge

## Where the branch stands

The branch stands on 'issue-64-engagement' (921c56e), which stands
on 'issue-63-candidates', which stands on 'dev'. Merge #63, #64,
then this branch, in order.

## The vocabulary of the issue against the vocabulary of the spec

The issue predates docs/spec/battle-engine-protocol.md and predates
the retirement of the Python engine (#73, commit b406d78). This
table binds the two.

| Issue word | Spec word |
|---|---|
| command 'step' | command 'act': 'unit_id', 'action', 'reaction', 'dice' |
| the state of 'step' | the session board, built by 'init' or by 'load' |
| the dice input, forced or sampled | the field 'dice' of 'act': 'mode' 'forced' with 'outcomes', or 'mode' 'sampled' |
| a sampled call takes a seed | the field 'seed' of 'init' builds the session random source; every sampled 'act' draws from it |
| 'model.py' lines 777 to 860 | the phase start, the pending units, the phase rotation, the stage event table |
| the play mode advances the board through 'step' | the page posts /api/act; 'EngineSession' sends 'act' and reads the board back with 'export' |

## Change summary

The engine runs the turn around the engagement, and four commands
of the contract answer: 'init', 'act', 'export', and 'load' with
the session content that it lost before.

New:

- 'engine/battle/turn.go': 'Board.Act' runs one decision and the
  turn cycle after it. 'Board.PendingUnits',
  'Board.AdvanceUntilPending', 'Board.BeginPhase', the debuff
  expiry, and the guard that stops a board on which no side can
  act.
- 'engine/battle/events.go': the domain types of the stage event
  table, the two triggers (kill, turn start) and the two effects
  (spawn, weaken), and the two firing points: after the activation
  and at the start of a turn.
- 'engine/battle/dice.go': 'Scripted' reads the outcome list of the
  wire form and reports a short list; 'Sampled' draws from a PCG
  source that the seed builds, and 'Sampled.Clone' keeps the place
  of the stream.
- 'engine/server/act.go': the command 'act'. It runs on a clone of
  the board and installs the clone when the whole run succeeds.
- 'engine/battle/codec.go': 'DecodeInit', 'EncodeState',
  'DecodeEvents', 'DecodeOutcomes', 'EncodeResolution',
  'EncodeSummary', 'EncodeRules', 'EncodeFaction'.
- 'engine/battle/resolve.go': 'Board.StrikeReactions', the query
  that binds the field 'reaction' of 'act' to the answer of
  'reactions'.
- 'tests/fixtures/engine/turn_cycle_board.json' and
  'turn_start_board.json': 4 'act' checks against the Python
  oracle, plus the three codec checks of the format.
- Hand-written Go tests: 'turn_test.go' (14), 'events_test.go' (6),
  'dice_test.go' (5), 'server/act_test.go' (12),
  'server/session_test.go' (6 more).
- 'tests/test_sandbox_ui.py': the page plays a battle end to end
  against the built binary, and one seed gives one battle.

Changed:

- 'Board' carries 'Events', 'PendingEvents' and 'FiredEvents', and
  'Board.Clone' and 'Unit.Clone' copy what one activation writes.
  'Board.PhaseIndex' reads the new 'phaseSlot'.
- 'engine/protocol/types.go': the terrain fields of 'Board'; the
  typed 'Events' and 'Rules' of 'InitRequest'; 'BoardSummary';
  'StrikeEvent', 'StageEventFired', 'PhaseEvent'; the outcome
  labels; the rules, the event table and the seed of 'export' and
  'load'. The protocol version goes to 1.3, because the change adds
  fields.
- 'engine/server/session.go': the session holds the event table as
  it arrived, the victory conditions, the deploy cells, the seed
  and the random source.
- 'docs/spec/battle-engine-protocol.md': 'init', 'act', 'export'
  and 'load'; the new section 'Turn cycle' with the stage event
  value sets; the terrain of 'init'.
- 'docs/reference/terminology-map.md': turn cycle, phase, phase
  start, pending unit, stage event, session random source,
  scripted roll.
- 'src/ggge_ai/engine/session.py': 'load' carries the rules, the
  event table and the seed; the seed reaches the page through
  '--seed'.
- 'src/ggge_ai/engine/codec.py': '_stance' no longer reads
  'Stance.NONE'.
- 'src/ggge_ai/engine/fake.py': the board summary carries the
  'pending' field of the contract, always empty.

## Call chain

'init': the handler decodes the request, 'battle.DecodeInit' builds
the board with its terrain, its rules and its event table, and the
session takes the victory conditions, the deploy cells and a random
source that the seed builds.

'act': 'boardOf' checks the session and decodes the request;
'activation' merges the request reaction into the decision;
'Server.dice' builds 'Scripted' or a clone of the session
'Sampled'; the handler clones the board; 'reactionFits' reads
'Board.StrikeReactions' and holds the necessity rule of the
contract; 'Board.Act' runs 'Board.Apply' (#64), then
'eventsAfterAct', then 'AdvanceUntilPending'; a short outcome list
of 'Scripted' throws the clone away; the answer is
'EncodeResolution' and 'EncodeSummary'.

'export': 'EncodeState' plus the rules, the event table as it
arrived, and the seed. 'load' takes the same five fields back.

The page: /api/act -> 'EngineSession.act' -> 'act' -> 'export'.
'EngineSession.pending_decision' then asks 'actions' for each unit
of the new phase, so the page follows the rotation without a rule
of its own.

## Exported Go API

    func (b *Board) Act(Decision, Dice) (Resolution, error)
    type Resolution; type Rotation
    func (b *Board) PendingUnits(Faction) []*Unit
    func (b *Board) AdvanceUntilPending() []Rotation
    func (b *Board) BeginPhase(Faction)
    func (b *Board) Clone() *Board
    func (u Unit) Clone() Unit
    func (b *Board) StrikeReactions(Decision) ([]Reaction, error)
    type TriggerKind; type EffectKind
    type Trigger; type Effect; type StageEvent; type EventTable
    type Scripted; func NewScripted([]bool) *Scripted
    func (s *Scripted) Lands(Node, float64) bool
    func (s *Scripted) Short() bool
    type Sampled; func NewSampled(int64) *Sampled
    func (s *Sampled) Clone() *Sampled
    func (s *Sampled) Lands(Node, float64) bool
    func DecodeInit(*protocol.InitRequest) (*Board, error)
    func EncodeState(*Board) protocol.BattleState
    func DecodeEvents(protocol.EventTable) (EventTable, error)
    func DecodeOutcomes([]string) ([]bool, error)
    func EncodeResolution(Resolution) []any
    func EncodeSummary(*Board) protocol.BoardSummary
    func EncodeRules(Rules) protocol.Rules
    func EncodeFaction(Faction) protocol.Faction

## Rules that diverge from the Python oracle

On top of the six of #64:

7. A destroyed unit stays on the board with no hit points left, and
   Python removed it. The differential op filters its answer on
   life, and the expectation of Python holds the same units in the
   same order.
8. A spawn skips an identity that the board holds, so a spawn of a
   unit that this battle destroyed puts nothing on the board. In
   Python that identity was gone, and the spawn ran. No fixture
   spawns such an identity.
9. A trigger or an effect outside the two value sets is a decode
   error. Python ran the table at every node and passed an unknown
   type in silence.
10. The phase start reads the living units of the side. Python read
    every unit of the side, and its list held no destroyed unit at
    that moment, so the two agree.

## Contention points for the reviewer

1. Spec addition: 'export' and 'load' carry the rules, the event
   table and the seed. Reason: the section calls them the snapshot
   of the session, and a session that loses the three answers other
   numbers than the one that 'export' read. #64 left the same point
   open (its contention 4). The three are optional on 'load', so a
   payload of the build before this branch still loads.
2. Spec addition: the shapes of 'events' and 'board' in the answer
   of 'act', the outcome labels 'hit' and 'miss', and the value
   sets of a stage event trigger and effect. The contract named the
   fields and left the shapes to the issue that implements them.
3. Spec addition: the section 'Turn cycle'. The contract described
   no phase rotation at all.
4. Oracle use: the two new fixtures come from one run of the
   historical Python model, in a scratch worktree of b406d78~1,
   deleted after the run. The note of each file records the origin
   commit. Everything else in the branch comes from the spec and
   from docs/reference/combat-formulas.md.
5. Defect on 'dev', worked around here: 'codec._stance' read
   'Stance.NONE', and b406d78 took that value out of the enum, so
   every valid reaction raised AttributeError on decode. The page
   cannot play a battle without the fix. One line, in this branch.
   No defect of #63 or #64 was found.
6. 'act' holds the necessity rule of the reaction, and
   'Board.Apply' does not: a nil reaction stays legal in the domain
   because a search settles that node somewhere else (#64). The
   cost is one more call of 'Board.Reactions' for each attack.
7. The activation runs on a clone of the board. A short outcome
   list shows up only when the resolution asks for the outcome that
   is not there, and the contract says that an error response
   changes no board. The clone also carries the rollback of a later
   issue. The cost is one board copy for each 'act'.
8. #64 contention 3 says that #65 must not land a sampler before
   #47 settles the per-supporter roll. The sampler here settles one
   volley with one draw, exactly as 'Forced' does, so #47 changes
   the node count for both dice at the same time.
9. The engine reads no victory condition in 'act'. A board with one
   side gone answers like any other, and the client decides that
   the battle is over. Both end-to-end tests hold that rule
   themselves. The victory conditions arrive with 'init' and wait
   for the advisor issue.

## Verification

- From 'engine': go vet clean; go test ok (battle, differential,
  protocol, server), also with -count=2; gofmt clean.
- uv run ruff check src tests scripts: all checks passed.
- uv run pytest -q: 990 passed, 4 skipped.
- The four 'act' checks of the two new boards matched the oracle on
  the first run. A one-point change of the energy regeneration
  fails three of them.
- The page plays a battle to its end against the built binary, and
  two runs under the seed 42 give the same event lists while the
  seed 43 gives another.
- By hand, against the built binary and the placeholder scenario of
  28 units: 60 activations through /api/act, the phases ally and
  enemy of the turns 1 to 3, and one enemy destroyed. No adb and no
  device: this is a code-only task.
- go test -race: clean on all four packages.

## Open points

- 'Board.Roster' still panics, and 'deploy_cells', 'place',
  'roster', 'rollback', 'set_unit', 'advice' and 'certify' answer
  not_implemented. The session already holds the victory conditions
  and the deploy cells of 'init' for them.
- 'export' of a board with terrain writes the two engine-only
  fields, and 'codec.decode_state' on the Python side refuses a
  field it does not hold. No scenario of the page carries terrain
  today. The Python mirror needs the two fields, or a documented
  skip, before a terrain map reaches the page.
- The snapshot does not carry the place of the random source in its
  stream, so a replay draws the same numbers only from the start of
  the battle.
