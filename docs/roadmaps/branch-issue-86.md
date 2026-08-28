# Branch roadmap: issue 86, the board contract apart from its implementation

> Type: working—deleted at merge

Issue: #86. Branch: issue-86-board-package. Status: awaiting-review.

## Change summary

Four commits.

| Commit | What |
|---|---|
| 7c9fd64 | This file |
| c294023 | The split: 43 files, +1832 / -1675, a pure move |
| 7530578 | The interfaces renamed 'BoardReader' and 'BoardResolver' on the user's ruling |
| (next) | The interfaces narrowed to the six methods the server calls; the board exports its own state and summary |

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

## The interfaces

    battle.BoardResolver Act
    battle.BoardReader   Capabilities ReachableCells ResponseAttacks
                         Clone State Summary
    battle.Board         BoardReader plus BoardResolver; 'Clone()'
                         returns Board

Rule (user ruling 2026-08-28): a method is on the interface because
a consumer outside 'board' calls it today. The server calls 'Act',
'Capabilities', 'ReachableCells', 'ResponseAttacks' and 'Clone', it
exports the state ('State()', the 'export' command) and it reads
the summary ('Summary()': turn, phase, pending, gone, for the 'act'
and 'init' answers). The board exports itself, so the codec reads
the struct and no field becomes an accessor on the contract.
'Apply' and 'Advance' are the two halves of 'Act' and stay on the
concrete type: 'load' calls 'Advance' on the value it decodes, and
the differential replay calls 'Apply' on the concrete type.

'var _ battle.Board = (*board.Board)(nil)' pins the implementation.
The result types the interface methods return live in
'battle/board.go'; 'State' and 'Summary' return the wire types of
'engine/protocol'.

## Call chain of the server

    server.session.board  battle.Board
      board.DecodeInit / board.DecodeState   -> *board.Board
      b.Act                                  BoardResolver
      b.Capabilities / b.ReachableCells /
      b.ResponseAttacks / b.Clone            BoardReader
      b.State() / b.Summary()                BoardReader, the wire form

## Verification

- 'go vet ./...': clean. 'gofmt -l .': empty.
- 'go test -race -count=1 ./...': five packages ok; the goldens under
  'tests/fixtures/engine/' pass unchanged.
- 'uv run pytest -q': 1027 passed, 4 skipped. 'ruff': clean.
- A second, independent gate run and the code review are recorded
  below when they land.

## Contention points

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
  #85, on this merge.
