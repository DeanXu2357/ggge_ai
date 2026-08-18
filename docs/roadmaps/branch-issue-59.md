# Branch roadmap: issue 59, the battle engine contract

> Type: working—deleted at merge

## Goal

Land the battle engine process shell and its full external
contract. No game logic. No search.

## Resume point

The contract draft holds every behavior of the 2026-08-19 round.
One open point waits for the user: the device behavior when the
defender cannot counter. See "Open points".

## Open points

1. The reaction menu when the attacker stands out of the range of
   the defender. Reading A: the counter buttons leave the menu,
   and dodge and defend stay. Reading B: no menu appears. #56 shows
   the menu holds no decline button, so neither reading needs a
   'none' stance. Reading B needs one more line in the spec: the
   trigger of an empty reaction list is more than a map weapon.

## Progress log

- 2026-08-19: worktree created; roadmap started.
- 2026-08-19: user stated nine behaviors. The engine holds the
  board, so the earlier stateless decision is dropped. Wrote
  docs/spec/battle-engine-protocol.md and the terminology entries.
