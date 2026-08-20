# Branch roadmap: issue 61, the board geometry

> Type: working—deleted at merge

## Change summary

The engine holds the board geometry with orthogonal movement,
orthogonal range and a footprint of more than one cell, and it
answers 'reach'. This supersedes #58.

New:

- 'engine/battle/geometry.go': the port of 'sandbox/model.py' 411
  to 535 on four steps, with the footprint rule.
- 'engine/battle/geometry_test.go': the hand-authored cases.
- 'engine/server/session.go': the board holder, 'load', and
  'reach'.
- 'engine/protocol/state.go': the field 'size' of a unit.

Changed:

- 'scripts/sandbox_ui.py': the page asks the engine for the reach
  of the selected unit and paints it as its own layer.
- 'docs/spec/battle-engine-protocol.md': the section 'Board
  geometry'; 'reach' answers an ordered list of anchor cells.
- 'docs/reference/ui-spec.md': the device reading of the movement
  range, and the footprint ruling.
- 'docs/reference/terminology-map.md': the bindings 'footprint' and
  'anchor cell'.
- 'src/ggge_ai/sandbox/model.py' and 'src/ggge_ai/engine/codec.py':
  the field 'size' as data. The Python geometry does not read it.
- The protocol version: 1.0 to 1.1.

## Device evidence

Stage 'uc_hard_1', turn 1, unit 鋼彈F90 (A.D.S.), frame
'assets/screenshots/20260819-020154.png', run
'data/runs/20260819-020001'.

The highlighted cells make a diamond, not a square. The row four
cells above the unit holds one highlighted cell, at column offset
-1. A Chebyshev range of the same radius fills that row from -5 to
+5. The two cells at offset 0 and +1 in that row carry enemy units.
The device therefore reads Manhattan, and the port matches it.

## What the footprint rule changed

The user ruled on 2026-08-20 that a unit covers a rectangle of
cells: a footprint of 2 by 2 and of 2 by 3 exists, the stage
decides which, and a unit does not turn. The field 'pos' is the
anchor: the cell of the footprint with the least value on each
axis.

Distance is now the least distance between a cell of the one
footprint and a cell of the other. Four results move:

1. A weapon reads the near cell of the footprint. A foe that
   touches a 2 by 2 unit is at distance 1, not at the 2 or 3 of
   the anchor.
2. A 'range_min' of 2 or more works against its own unit. The
   large unit cannot fire a long weapon at a foe that touches it,
   because that foe reads distance 1.
3. 'reach' answers anchor cells. A unit moves as one body: each
   step carries the whole footprint, so one blocker denies every
   anchor whose footprint covers it, and the last row and the last
   column of the board hold no anchor of a footprint of 2.
4. The support finders and the blast read the footprint. A wide
   supporter joins an engagement that its anchor alone could not
   reach.

A board that carries no 'size' gives the unit one cell, so every
case of the orthogonal port keeps its answer.

## Verification

- cd engine && go vet ./... : no finding.
- cd engine && go test ./... : ok, five packages.
- uv run ruff check src tests scripts : all checks passed.
- uv run pytest -q : 1112 passed, 4 skipped.

No differential case: the Python model keeps the diagonal (ruling
2026-08-18) and gives every unit one cell (ruling 2026-08-20), so
a comparison that reads the distance or the footprint proves
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
6. 'model.py' and 'codec.py' carry the field 'size', and the
   Python geometry does not read it. The parity test
   'tests/test_engine_codec.py' compares the fields of the
   dataclass with the JSON tags of the Go struct, so a field that
   the engine holds and the model does not is a test failure. The
   field is data, not a rule: the ruling of the day keeps the
   Python geometry at one cell.
7. The protocol version is 1.1. The contract says that a change
   which adds a field raises the version.
8. The spec said that the blast of a skill is a Chebyshev radius.
   The port measures the blast on the board distance, as
   'blast_victims' does after the orthogonal correction, so the
   spec now names the board distance. This is a drift that the
   orthogonal commit left behind.

## Open points

1. No one has compared an engine 'reach' answer cell by cell
   against a device frame of the same board. The device reading
   confirms the shape of the rule, not the cells of one board.
2. No device frame in this project shows a unit of more than one
   cell. The footprint rule rests on the user ruling of
   2026-08-20.
3. Nothing writes the field 'size'. The stage definition and the
   intel store give no footprint yet, so every board that the
   project builds today carries one cell for each unit.
4. The sandbox web page draws one cell for each unit and maps one
   click to one cell. The page needs the footprint before a large
   unit is legible there. Issue #70 holds that work.
