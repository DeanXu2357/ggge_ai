# Branch roadmap: issue 65, the turn cycle and the act command

> Type: working—deleted at merge

## Where the branch stands

The branch stands on 'issue-64-engagement' (921c56e), which stands
on 'issue-63-candidates', which stands on 'dev'. Merge #63, #64,
then this branch, in order.

## The vocabulary of the issue against the vocabulary of the spec

The issue predates the spec docs/spec/battle-engine-protocol.md and
predates the retirement of the Python engine (#73, commit b406d78).
This table binds the two.

| Issue word | Spec word |
|---|---|
| command 'step' | command 'act': 'unit_id', 'action', 'reaction', 'dice' |
| the state of 'step' | the session board, built by 'init' or by 'load' |
| the dice input, forced or sampled | the field 'dice' of 'act': 'mode' 'forced' with 'outcomes', or 'mode' 'sampled' |
| a sampled call takes a seed | the field 'seed' of 'init' seeds the session random source; every sampled 'act' draws from it |
| 'model.py' lines 777 to 860 | the phase start, the pending units, the phase rotation, the stage event table |
| the play mode advances the board through 'step' | the page posts /api/act; 'EngineSession' sends 'act' and reads the board back with 'export' |

## Plan

1. The turn cycle in the domain package: the pending units, the
   phase start, the debuff expiry, the rotation, the stage event
   table.
2. The dice: 'Scripted' for the wire 'forced', 'Sampled' for the
   session random source.
3. The commands: 'init', 'act', 'export', and the rules, the event
   table and the seed on 'load'.
4. The Python side and the page play mode.
5. The fixtures and the tests.

## Progress log

- Worktree added, state block filled.
