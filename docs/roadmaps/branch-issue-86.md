# Branch roadmap: issue 86, the board contract apart from its implementation

> Type: working—deleted at merge

Issue: #86. Branch: issue-86-board-package. Status: awaiting-review.

## Change summary

Eleven commits.

| Commit | What |
|---|---|
| 7c9fd64 | This file |
| c294023 | The split: 43 files, +1832 / -1675, a pure move |
| 7530578 | The interfaces renamed 'BoardReader' and 'BoardResolver' on the user's ruling |
| d5c32ff | The interfaces narrowed to the six methods the server calls; the board exports its own state and summary |
| 4c50706 | The spec names the contract methods and the protocol import |
| ac8aaeb | The twelve methods only the package calls made private; two policy comments deleted from 'model.go' |
| 91ccc00, 9672ecf | The terminology map points at the private names; the narrating comment on 'Cell.Before' deleted |
| 8709ad3 | The contract speaks the protocol on every method; the domain model moves into 'board'; the server runs no codec |
| 8f362e7 | The map's Go references follow; the artifact gains the cut-A commit and the sentinel |
| b9294e8 | The names of 'board' that nothing outside calls made private: 27 files, the model and the result types |

    engine/battle          model.go (the data types, the six sentinel
                           errors), board.go (the interfaces and the
                           result types), terrain.go, dice.go
    engine/battle/board    board.go (the struct, 'New', the accessors,
                           the lookups), resolve.go, response_attacks.go,
                           turn.go, forecast.go, candidates.go,
                           geometry.go, clone.go, codec.go, and the
                           formulas damage.go, hit.go, rules.go,
                           strike.go, unchanged, for issue #85

The contract package imports nothing under 'engine/'. 'board'
imports 'battle' and 'protocol'. 'server' holds 'battle.Board' in
the session, constructs through 'board.DecodeInit' and
'board.DecodeState', and calls the codec through 'board.Encode*'
and 'board.Decode*'. 'differential' reads 'Roster()' in place of
the field and imports the formulas from 'board'.

## The interfaces (cut A, user ruling 2026-08-28)

    battle.BoardReader   Capabilities(unitID) protocol.ActionsResponse
                         ReachableCells(unitID) []protocol.Cell
                         ResponseAttacks(*protocol.Decision, defenderID)
                             protocol.ResponseAttacksResponse
                         Clone() Board
                         State() protocol.BattleState
                         Summary() protocol.BoardSummary
    battle.BoardResolver Act(*protocol.Decision, Dice) []any
    battle.Board         BoardReader plus BoardResolver

The contract speaks the wire types of 'engine/protocol' on every
method. 'engine/battle' holds the three interfaces, the dice,
'DecodeOutcomes' and the six sentinel errors, and nothing else. The
domain model ('Unit', 'Pilot', 'Mech', 'Weapon', 'Decision', the
result types) is the implementation's own, in 'engine/battle/board',
with the codec internal to it. The server constructs with
'board.DecodeInit' or 'board.DecodeState' and otherwise passes the
request payloads to the board as they are.

The path here: the first cut exposed 24 read methods and the
codec's reads as accessors (rejected); the second cut kept six
domain-typed methods beside two wire-typed ones and left nine codec
calls in the server (rejected as half of each). Cut B, a codec
package apart, needs the rejected accessors, so A was chosen.

## Call chain of the server

    server.session.board  battle.Board
      board.DecodeInit / board.DecodeState   -> *board.Board
      b.Act(&request.Action, dice)           BoardResolver
      b.Capabilities / b.ReachableCells /
      b.ResponseAttacks / b.Clone            BoardReader
      b.State() / b.Summary()                BoardReader
    no Encode or Decode call in the server

## Verification

- Gates green at every commit of the branch (the editor's run and
  a separate run at c294023; separate runs at ac8aaeb and at 9672ecf, both green).
- The goldens under 'tests/fixtures/engine/' pass unchanged.
- The main session read 'engine/battle/board.go' in full at d5c32ff
  and at ac8aaeb, grepped every method call on the session board in
  'engine/server' (Act, Capabilities, Clone, ReachableCells,
  ResponseAttacks, State, Summary; Advance on the concrete value in
  'load'), and listed the exported methods of '*board.Board' against
  their outside callers. The interface text in this artifact is the
  file's.
- The first report of this branch relayed the editor's summary
  without that read; the user found the 24-method reader and the
  accessors. The ledger records it (0828).

## Contention points

0. **'protocol.ErrOutsideContract'.** Once the action decodes
   behind the interface, the server could not tell a malformed
   payload from an illegal action, and the spec requires
   'bad_request' for the former. The board wraps its two decode
   refusals in this sentinel and the server maps it first. The two
   refusal messages changed to name the contract.

1. **The first cut leaked the codec's reads onto the contract** as
   accessors ('Bounds', 'DefaultTerrain', 'TerrainCells', 'Roster',
   'Pending', 'Gone', 'Turn', 'Phase'). The user rejected it on
   review. The board now exports itself ('State', 'Summary'), and
   the struct fields are unexported and read only inside 'board'.
2. **The interfaces are narrowed to the callers**, on the user's
   ruling of 2026-08-28, against the issue text that fixed the
   method set at the 22 that existed. The issue closes on the
   narrowed set; the ruling is in the ledger.
3. **The codec lives with the implementation.** 'server' imports
   'board' to construct ('DecodeInit', 'DecodeState') and for the
   codec of decisions, cells, capabilities and engagements
   ('Decode*', 'Encode*' over contract types). The state and the
   summary come from the board itself.
4. **'Roster()' and 'TerrainCells()' hand out the live slice and
   map**, as the exported fields did. Now that they are part of a
   contract, a caller could mutate the board behind it. A copy
   costs an allocation per call; not changed here.
5. **'cloneAmount' is duplicated**: 'battle' keeps it for
   'Unit.Clone', 'board/codec.go' has an unexported copy, to keep a
   five-line helper out of the contract.
6. **'geometry.go' went to 'board' in full.** Nothing in it reads
   the board, but nothing outside 'board' calls it either.
7. Six files show as add plus delete in the commit, not rename: the
   package qualification pushed similarity under git's threshold.
   'git log --follow' tracks them.

## Deferred

- The formulas move out of 'board' into their own package: issue
  #85, on this merge. 'StanceMultiplier' is exported over a private
  parameter type until then, so it is uncallable from outside; #85
  settles it with the rest.
- The fields of 'Unit', 'Pilot', 'Mech' and 'Weapon' stay exported
  because the differential formula tests set them. Once #85 gives
  the formulas their own input type, those four types and their
  fields can go private too.
