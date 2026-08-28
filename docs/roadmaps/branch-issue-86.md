# Branch roadmap: issue 86, the board contract apart from its implementation

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-86-board-package' starts from 'dev' (692f511),
after the merge of #84. Issue #85 waits for this merge.

## The shape (user decision 2026-08-28)

    engine/battle          the contract: the data types, 'Board' as
                           interfaces (a read side and an act side),
                           the errors, the dice, 'Terrain'
    engine/battle/board    the implementation: the 'Board' struct and
                           its 22 methods, resolve, response attacks,
                           turn, forecast, candidates, geometry,
                           clone, the codec, and, for now, the formulas

'board' imports 'battle' and 'protocol'. 'server' imports 'battle'
for the interfaces, the types, the errors and the dice, and 'board'
to construct. No cycle.

## Facts that shape the interfaces

- 'engine/server/initbattle.go' reads the fields 'board.Turn' and
  'board.Phase'. The read side gives 'Turn()' and 'Phase()'.
- 'engine/differential/resolve_test.go' iterates 'board.Units'. It
  reads 'Roster()' instead.
- Every other use outside 'battle' is a method call, a constructor,
  a codec function, a type, an error or a dice type.
- All 13 test files of 'battle' are 'package battle' (internal).
  Tests move with the code they test.

## Plan

1. The split, one commit if the gates stay green throughout.
2. The spec section "Process model" names the two packages. A
   terminology binding if a new term appears.
3. Gates, review, artifact.

## Resume point

Step 1 is delegated to the code editor.

## Progress log

- 2026-08-28: worktree added, roadmap written.
