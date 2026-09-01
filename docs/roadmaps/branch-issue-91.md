# Branch roadmap: issue 91, content and values

> Type: working—deleted at merge

Issue #91. Branch off 'dev' at 'b7055ac'.

## The design, ruled 2026-09-01

Only 'UnitValue', 'Phase' and 'Turn' change during a battle. The
state therefore splits into the two halves the signatures must show:

- 'state.Content', the invariants: the identity half of each unit
  ('Faction', 'Size', the six maxima, 'HasShield',
  'SupportDefendWhenAttack', the 'Mech' and 'Pilot' pointers), plus
  'Bounds', 'Terrain' and 'TerrainCells'.
- 'state.Values', the variables: 'Units []UnitValue', index-aligned
  with the content units, plus 'Phase' and 'Turn'.

The two writing systems become pure computations over the pair, and
neither depends on the other:

  engagement.Commit(content, values, decision, dice) (Values, Trace, error)
  turn.Advance(content, values) (Values, []Rotation)

'Advance' runs a phase rotation for any (content, values) pair: it
must not need a prior engagement. Each system copies the values
column at its entry and never writes its inputs. A refusal returns
before any change.

'Board.Act' is the four ruled steps and nothing else:

1. The changes of the engagement: 'Commit'.
2. The changes of the turn end: 'Advance', fed the answer of step 1.
3. One application of both: assign the final column to the board.
4. The event chain, assembled inline. No single-caller projection
   helper.

The wire does not move: no protocol change, no golden change, no
Python change.

## The mechanism

- The board stores the pair: 'content state.Content' and
  'values state.Values'. The type 'state.Battle' keeps its exact
  current shape and becomes the transient working form, so no rule
  and no rule test changes its body.
- 'state.Compose(content *Content, values Values) Battle' builds the
  working form. Compose is the entry copy: it deep-copies the slices
  of each 'UnitValue' ('Skills' with their amounts, 'MapWeaponAmmo',
  'Debuffs'), so the working form aliases nothing of the input
  column. The definition data is shared, as everywhere.
- '(b *Battle).Column() Values' extracts the column back out. The
  working form owns its column exclusively after Compose, so the
  extraction moves the headers and copies nothing.
- 'engagement.Commit': Compose, 'prepare', the dice-cover check,
  'write', extract. The names 'prepare', 'write', 'draws', 'plan'
  and 'onPhase' stay inside the package; the entry keeps the name
  'Commit' because the write is the semantic of the call.
- 'engagement.Menu(content, values, decision, defenderID)': Compose,
  then the current body. 'Activatable' and 'LivingUnit' keep their
  shapes over the working form; the readers compose first.
- 'turn.Advance': Compose, rotate, extract. 'Pending' and 'Gone'
  keep their shapes over the working form.
- 'board.Load' and 'state.FromContract' answer the pair;
  'Board.State' composes and converts. 'geometry' is untouched: it
  reads the working form.

## What the change owes

- A test that 'Advance' runs standalone on a (content, values) pair
  that no prior 'Commit' produced.
- A test that the answered column shares no writable memory with the
  input column.
- The existing refusal test keeps passing with its meaning intact.
- 'git diff' on 'tests/fixtures' is empty and the protocol version
  stays "2.0".
- The spec process-model section and the terminology map move in the
  same change: the conversion bullet, the board bullet, the state
  helper list, and the rows for 'state package' and 'unit value',
  plus the new bindings 'content' and 'values'.
- Gates: gofmt, go vet, go test -race, pytest, ruff.

## Progress log

- 2026-09-01: issue #91 opened from the session design; branch
  opened at 'b7055ac'. The uncommitted session draft was discarded
  on the user's word; this branch rebuilds from clean 'dev'.

- 2026-09-01: the code editor delivered the implementation: the
  state pair, 'Compose' and 'Column', the pure 'Commit' and
  'Advance', the four-step 'Act', the tests and the two documents.
  All gates green. Open decisions of the delivery: 'UnitContent' as
  the per-unit invariant type; a refusal answers the zero column;
  the term 'commit phase' renamed to 'write phase'; the bindings
  'content' 內容 and 'values' 值欄 are proposals, not rulings.

## Resume point

The code review and the finish steps.
