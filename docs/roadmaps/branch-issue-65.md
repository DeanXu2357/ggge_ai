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

The plan is docs/roadmaps/branch-issue-65-plan.md (nine tasks). No
task has started. Execute in order; each task ends in one commit.

## Progress log

- 2026-08-27: worktree added, rulings recorded, plan written.
