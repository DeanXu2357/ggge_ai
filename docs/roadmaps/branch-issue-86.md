# Branch roadmap: issue 86, the board contract apart from its implementation

> Type: working—deleted at merge

Issue: #86. Branch: issue-86-board-package. Status: awaiting-review.

## Change summary

Two commits.

| Commit | What |
|---|---|
| 7c9fd64 | This file |
| c294023 | The split: 43 files, +1832 / -1675, a pure move |

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

    battle.Reader    Activatable BlockingCells Bounds ByFaction
                     Capabilities Clone CounterWeapon DefaultTerrain
                     Gone OccupiedCells Pending Phase PhaseIndex
                     ReachableCells ResponseAttacks Roster
                     SupportAttackers SupportDefenders TargetsOf
                     TerrainAt TerrainCells TerrainOf Turn Unit
    battle.Resolver  Act Advance Apply
    battle.Board     Reader plus Resolver; 'Clone()' returns Board

'var _ battle.Board = (*board.Board)(nil)' pins the implementation.
The result types the methods return moved to 'battle/board.go':
'CellSet', 'Forecast', 'Capabilities', 'StrikeKind', 'Strike',
'Trace', 'Rotation', 'Resolution', 'SupportAttacker',
'ResponseAttackOption', 'SupportDefendOption',
'SupportAttackOption', 'SideOptions', 'Engagement'.

## Call chain of the server

    server.session.board  battle.Board
      board.DecodeInit / board.DecodeState   -> *board.Board
      b.Act / b.Apply / b.Advance            Resolver
      b.Roster / b.Pending / b.Gone / ...    Reader
      board.EncodeState(b) / EncodeSummary   take battle.Board

## Verification

- 'go vet ./...': clean. 'gofmt -l .': empty.
- 'go test -race -count=1 ./...': five packages ok; the goldens under
  'tests/fixtures/engine/' pass unchanged.
- 'uv run pytest -q': 1027 passed, 4 skipped. 'ruff': clean.
- A second, independent gate run and the code review are recorded
  below when they land.

## Contention points

1. **Five accessors, not two.** 'Turn()' and 'Phase()' were planned.
   'Bounds()', 'DefaultTerrain()' and 'TerrainCells()' joined them
   because 'EncodeState' must read them through the interface the
   session holds. The alternative, a type assertion to the struct
   inside the codec, was rejected. The six struct fields are now
   unexported: Go forbids a field and a method of one name.
2. **'Reader' is wide: 24 methods.** Twelve are called by nobody
   outside 'battle' and 'board': 'Activatable', 'BlockingCells',
   'ByFaction', 'CounterWeapon', 'OccupiedCells', 'PhaseIndex',
   'SupportAttackers', 'SupportDefenders', 'TargetsOf', 'TerrainAt',
   'TerrainOf', 'Unit'. The issue fixed the method set at the 22
   that existed; a narrower 'Reader' is a separate decision.
3. **The codec lives with the implementation.** 'server' therefore
   imports 'board' in three files, for the codec and not only to
   construct. 'Encode*' take the interface now, so they could move
   up to the contract later; 'Decode*' build the struct and stay.
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
- Narrowing 'Reader' (point 2), if the user wants it.
