# Branch roadmap: issue 65, the turn cycle and the act command

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-65-turn-cycle-v2' starts from 'dev' (1de115e),
after the merge of the #64 rebuild (49a5863). It replaces the
branch 'issue-65-turn-cycle', which stood on the pre-ruling #64 and
froze its fixtures from a Python run. That branch is off-limits to
this session: no file of it is read.

## Rulings of 2026-08-27

The user ruled on points 1 to 8 before the plan, and on point 9
during the merge review. Each one binds the branch.

1. Oracle. No Python run and no reuse of the two old fixtures. The
   expected states of the turn-cycle fixtures come by hand from
   docs/reference/combat-formulas.md and the spec. The note of each
   fixture cites the document lines.
2. Scope of the turn cycle: the phase rotation ally, third_party,
   enemy; the turn counter; the reset of the 'acted' flag; the EN
   regeneration of 10% of the maximum at the own phase start; the
   debuff expiry after one full round. The stage event table, the
   chance steps and the support charges stay out. 'init' accepts
   'events' and stores it unread. A new issue takes the three after
   a spec shape lands.
3. Commands: 'init', 'act', 'export'; 'load' gains the seed. No
   'rollback' here: 'act' writes the history entry, and the command
   waits for its issue.
4. Branch: 'issue-65-turn-cycle-v2' off 'dev'. The old branch and
   its worktree stay for the user to delete after the merge.
5. EN rounding: floor. The spec marks the rule as a hypothesis with
   combat-formulas.md:310 as the source; a device measurement
   settles it later.
6. Victory: the engine judges no refusal on a finished board. The
   board summary of 'act' and 'export' carries a field that names
   the side that is gone. The client stops on that field.
7. Page start: the page keeps 'load' plus a seed. 'init' lands per
   spec without 'place', with Go tests only; 'place' stays with its
   own issue.
8. Closure: the run of the web UI is dropped. The command mode
   plays one battle through the commands alone, in this loop: the
   phase of side A opens; A reads its pending units; A reads the
   menu of each unit with 'actions'; A decides; when the action
   names a target, A sends it to 'reactions' and reads the reaction
   list of the struck unit of side B; A sends both decisions to
   'act'; A continues with its other units; when every unit of A
   acted, the phase rotates to B, and B runs the same loop with the
   sides exchanged; the loop ends when one side is gone. The page
   attack path waits for issue #78; this branch changes no line of
   scripts/sandbox_ui.py.
9. Names of the new code of the branch. The branch renames the
   helpers 'activation' and 'roll' of the 'act' handler, because
   the branch introduces the two and 'act' is the only caller of
   each. It also renames the file 'engine/server/init.go' to
   'initbattle.go': every handler file of the package holds a
   'func init()' that registers its command, so the old name read
   as the initialization of the package and not as the handler of
   the wire command 'init'. The helper 'boardOf' is code of 'dev'
   with five callers after the merge, so it goes to issue #82 and
   lands after this branch merges.

Assumptions that the user did not rule on, stated here for the
review:

- The sampled dice settles one volley with one draw, as 'Forced'
  does. Issue #47 changes the node count for both at the same time.
- A debuff expires when the phase index reaches its applied phase
  index plus three (one full round), per combat-formulas.md
  lines 269 to 273.

## Resume point

All nine tasks, the final fix wave, and the two helper names of
'act' landed. The branch waits for the merge review of the user.

## Progress log

- 2026-08-27: worktree added, rulings recorded, plan written.
- Task 1: e79157b.
- Task 2: 590e34d.
- Task 3: 300a9fe..79570f6.
- Task 4: 7a61e1b.
- Task 5: 77ecb24..fd4f366.
- Task 6: 83dcfc3..960b998.
- Task 7: 69b5d90..028754a.
- Task 8: dcef418..7996ac5.
- Task 9: 81eac28..9aec841.
- Fix wave of the two reviews: fac0051..065fcec.
- Roadmap reworked into the review artifact: 51d3fac.
- Names of the two helpers of 'act', per ruling 9: 4c734d8.
- Name of the file of the 'init' handler, per ruling 9: 34b2c48.

## Final review

The two reviews of 2026-08-27 returned findings, and the controller
ruled on each. This wave changed:

- A1: 'export' answers 'gone', the sides with no living unit.
- A2: a reaction inside 'action' is a bad_request.
- A3: 'load' rotates a phase that holds no pending unit.
- A4: the session holds the 'pending_events' and the 'fired_events'
  of the loaded state unread, and 'export' echoes them.
- A5: 'DecodeInit' refuses a unit of 'enemies' that is no enemy, a
  footprint outside the bounds, and a terrain cell outside the
  bounds.
- A6: the answer of 'init' reads the phase of the board back.
- A7: 'ServerDraw' holds one 'rand.Rand' instead of building one
  for each draw.
- A8: the differential op 'act' refuses a short manual roll, like
  the server.
- A9: the terrain name comes from 'Terrain.String', and the cell
  order from 'SortedCells'.
- B1: a refused 'act' of an attack candidate tries the next
  candidate before the reposition or the standby.
- B2: 'FORCED_HITS' lives in play.py alone.
- B3: the module docstring of play.py says that '_steps' orders
  the picks and is not the distance of the board.
- B4: a null 'seed' of the fake load is 0.
- B5: the engine report of the page calls 'export', not a seedless
  'load' that replaced the live session.
- C1: the flow comments of act_test.go, act.go, turn_test.go are
  trimmed to their why-clause.
- C2 to C5: the spec, the terminology map, and this file.

## Evidence

The command mode ran two battles from seed 7 on the placeholder
scenario.

Sampled dice, 60 turns: turn 61, no side gone, 1680 activations,
1674 strikes, 0 landed (data/runs/20260827-120815).

Forced hits: turn 5, ally gone, 106 activations, 80 of 80 strikes
landed, 16 killed (data/runs/20260827-122738).

Both directories are gitignored run logs.

## Change summary

The engine runs the turn around the engagement of #64. 'Board.Act'
applies one decision through 'Board.Apply' and then rotates the
phase while the faction of the phase holds no pending unit. The
move from the enemy phase to the ally phase adds one to the turn.
The phase start gives the living units of the faction their
activation back and one tenth of the maximum EN, floored, and drops
the debuffs of one full round on every side. The chance steps, the
support charges and the stage events stay out (ruling 2).

Four commands answer: 'init', 'act', 'export', and 'load' with the
seed. 'act' runs on a clone of the board and installs the clone
when the whole run succeeds. The manual roll reads 'outcomes' in
the resolution order; the server draw reads one PCG source that the
seed builds, and its clone keeps the place of the stream. 'export'
answers the state, the history, the seed and the sides that are
gone. 'load' rotates a snapshot whose phase holds no pending unit.

New files:

- engine/battle/turn.go: 'Board.Act', 'Board.Advance',
  'Board.Pending', 'Board.Gone', the phase start.
- engine/battle/clone.go: 'Board.Clone', 'Unit.Clone'.
- engine/battle/dice.go: 'ManualRoll', 'ServerDraw' beside the
  node-keyed 'Forced' of the fixtures.
- engine/server/initbattle.go, engine/server/act.go: the two
  handlers.
- engine/differential/turn_test.go and the two hand-derived cases
  tests/fixtures/engine/turn_cycle_board.json and
  turn_pending_board.json.
- src/ggge_ai/engine/play.py, scripts/play_battle.py: the command
  mode of ruling 8; tests/test_engine_play.py.

Changed files:

- engine/protocol/types.go: the terrain of 'init', the two event
  shapes and the summary of 'act', 'HistoryEntry', the seed and
  'gone' of 'export', the seed of 'load'. Version 1.3 on both sides.
- engine/battle/codec.go: 'DecodeInit', 'EncodeState',
  'DecodeOutcomes', 'EncodeResolution', 'EncodeSummary',
  'EncodeFaction'. engine/battle/rules.go: 'ENRegenPercent'.
- engine/server/session.go: the session holds the seed, the draw,
  the history, the victory conditions, the event table and the
  deploy cells of 'init', and the event lists of 'load'.
- src/ggge_ai/engine/session.py: the seed of 'load'.
  src/ggge_ai/engine/fake.py: the summary shape and the seed.
  scripts/sandbox_ui.py: the engine report calls 'export', not
  'load'.
- docs/spec/battle-engine-protocol.md: 'init', 'act', 'export and
  load', the section 'Turn cycle', the hand-derived case.
  docs/reference/terminology-map.md: nine rows.

## Call chain

'load': the handler decodes the state, 'battle.DecodeState' builds
the board, 'Board.Advance' rotates a phase with no pending unit,
and 'newSession' takes the seed and builds the server draw.

'init': the handler decodes the request, 'battle.DecodeInit' checks
the board, the enemies and the terrain and builds the board at turn
1 in the ally phase; the session stores the victory conditions, the
event table and the deploy cells unread.

'act': 'boardOf' checks the session and decodes the request;
'activation' merges the request reaction into the decision after the
necessity gate; 'roll' builds a 'ManualRoll' or a clone of the
session 'ServerDraw'; the handler clones the board; 'Board.Act' runs
'Board.Apply' and then 'Board.Advance'; a short outcome list throws
the clone away; on success the handler installs the clone and the
draw, appends the history entry, and answers 'EncodeResolution' and
'EncodeSummary'.

'export': 'EncodeState' plus the history, the seed, the event lists
of the loaded state and 'Board.Gone'.

The command mode: 'Player.play' reads the state with 'export', takes
the first pending unit of the phase, reads its menu with 'actions',
orders the candidate attacks by '_steps', asks 'reactions' for each
candidate, sends the first accepted one to 'act' with the first
reaction the engine lists, tries the next candidate on a refusal,
falls back to a reposition or a standby, and stops on the field
'gone' of the answer.

## Contention points for the reviewer

1. The field 'rules' of 'init' is unread.
2. 'export' and 'load' carry the seed but not the event table, the
   victory conditions, or the deploy cells, so a session that
   'init' built and 'load' reloads loses the three (they are
   unread today).
3. The summary field 'gone' as the shape of ruling 6.
4. The necessity rule of the reaction lives in the 'act' handler.
5. The one-draw volley and #47.
6. The page attack path waits for #78, and the command mode is the
   closure per ruling 8.
7. The fixed 'ENRegenPercent' replaces 'ENRegenFraction'.
8. Finding: the accuracy values of the frozen fixtures (4.0 and
   5.0) and of the placeholder scenario (0.0 and 5.0) give a base
   hit rate under ten percent (engine/battle/hit.go reads accuracy
   as percentage points), and a dodge reaction subtracts 20 points
   and clamps to zero. A sampled battle on that data never ends.
   The values are placeholders, not measured intel. The
   to-the-end test and the evidence run use forced hits; the
   sampled mode carries the same-seed proof. The user decides
   whether the intel store or the fixtures get measured accuracy.
9. The command mode answers every attack with the first reaction
   the engine lists, which is 'dodge'. The choice of a reaction is
   a policy, not a rule; the loop holds none by design.
10. 'load' rotates a snapshot whose phase holds no pending unit;
    'init' does not, because the deploy phase waits for 'place'.
