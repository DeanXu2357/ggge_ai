# Branch roadmap: issue 65, the turn cycle and the act command

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-65-turn-cycle-v2' starts from 'dev' (1de115e),
after the merge of the #64 rebuild (49a5863). It replaces the
branch 'issue-65-turn-cycle', which stood on the pre-ruling #64 and
froze its fixtures from a Python run. That branch is off-limits to
this session: no file of it is read.

## Rulings of 2026-08-27

The user ruled on these points before the plan. Each one binds the
branch.

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

Assumptions that the user did not rule on, stated here for the
review:

- The sampled dice settles one volley with one draw, as 'Forced'
  does. Issue #47 changes the node count for both at the same time.
- A debuff expires when the phase index reaches its applied phase
  index plus three (one full round), per combat-formulas.md
  lines 269 to 273.

## Resume point

All nine tasks landed. The branch waits for the final review and
/finish-task.

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

## Evidence

The command mode ran two battles from seed 7 on the placeholder
scenario.

Sampled dice, 60 turns: turn 61, no side gone, 1680 activations,
1674 strikes, 0 landed (data/runs/20260827-120815).

Forced hits: turn 5, ally gone, 106 activations, 80 of 80 strikes
landed, 16 killed (data/runs/20260827-122738).

Both directories are gitignored run logs.

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
