# Branch roadmap: issue 61, the board geometry

> Type: working—deleted at merge

## Change summary

The engine holds the board geometry with orthogonal movement and
orthogonal range, and answers 'reach'. This supersedes #58.

New:

- 'engine/battle/geometry.go': the port of 'sandbox/model.py' 411
  to 535 on four steps.
- 'engine/battle/geometry_test.go': the hand-authored cases.
- 'engine/server/session.go': the board holder, 'load', and
  'reach'.

Changed:

- 'scripts/sandbox_ui.py': the page asks the engine for the reach
  of the selected unit and paints it as its own layer.
- 'docs/spec/battle-engine-protocol.md': 'reach' answers an
  ordered list.
- 'docs/reference/ui-spec.md': the device reading of the movement
  range.

## Device evidence

Stage 'uc_hard_1', turn 1, unit 鋼彈F90 (A.D.S.), frame
'assets/screenshots/20260819-020154.png', run
'data/runs/20260819-020001'.

The highlighted cells make a diamond, not a square. The row four
cells above the unit holds one highlighted cell, at column offset
-1. A Chebyshev range of the same radius fills that row from -5 to
+5. The two cells at offset 0 and +1 in that row carry enemy units.
The device therefore reads Manhattan, and the port matches it.

## Verification

- cd engine && go vet ./... : no finding.
- cd engine && go test ./... : ok, five packages.
- uv run ruff check src tests scripts : all checks passed.
- uv run pytest -q : 1111 passed, 4 skipped.

No differential case: the Python model keeps the diagonal (ruling
2026-08-18), so a distance-dependent comparison against it proves
nothing. Every case here is hand-authored or read from the device.

The web UI test pins that the engine cells are a strict subset of
the Python cells on the test board. Strict, not equal: an equal
answer would mean the layer never exercised the rule change.

## What the orthogonal rule changed

Six results move, and four of them are behavior a caller can feel:

1. 'nearest_free_cell' leaves the ring on a straight line. With
   the centre and its four neighbours taken it answers (-2,0); the
   king-step source answers (-1,-1). A caller that assumed a spawn
   stays inside one cell now gets a cell two steps out.
2. A blast of 1 is a plus of five cells, not a square of nine. A
   foe on the diagonal of the aim cell survives.
3. One blocker costs much more. On the 5 by 5 case an enemy on the
   straight path removes the blocked cell and the cell behind it,
   because the detour costs two extra steps where a king step cost
   none.
4. The support finders lost the diagonal. A supporter with
   move_range 1 that stands diagonally is at distance 2 and cannot
   join.
5. 'reachable_cells' gives 2r²+2r+1 cells, not (2r+1)²: 13 against
   25 at move_range 2.
6. The second key of the proximity tie-break changed meaning.
   Under Chebyshev it separated a corner from a side at an equal
   distance. Under Manhattan two cells at an equal board distance
   are ranked by the square of the straight line, so (1,1) beats
   (0,2) against the anchor (2,2). The port keeps the key of the
   source and pins the order in a test.

## Contention points

1. The session holds one board and nothing else: no deploy cells,
   no 'place', no roster, no history, and therefore no 'rollback'.
   'load' takes the history field of the contract and drops it,
   because no history exists to fill.
2. 'reach' answers an ordered list. The contract said nothing, and
   a set has no wire order. The order is the ported proximity key,
   anchored at the cell of the unit.
3. A request decodes with an unknown field allowed, while a
   differential case does not. The contract says a change adds a
   field, so an old build must not refuse a newer payload.
4. Unit identity is a pointer into the state slice. The Python
   source compares with 'is'.
5. The page paints the engine cells as a second layer and does not
   move the click targets. The engine set is inside the Python set,
   so the page offers no cell that the play path refuses.

## Open point

No one has compared an engine 'reach' answer cell by cell against
a device frame of the same board. The device reading confirms the
shape of the rule, not the cells of one board.
