# Branch roadmap: issue 59, the battle engine contract

> Type: working—deleted at merge

## Goal

Land the battle engine process shell and its full external
contract. No game logic. No search.

## Resume point

The contract is settled. The next step is the code of the shell:
the Go module, the envelope, 'hello', 'ping', the declared
commands, and the Python client.

## Progress log

- 2026-08-19: worktree created; roadmap started.
- 2026-08-19: user stated nine behaviors. The engine holds the
  board, so the earlier stateless decision is dropped. Wrote
  docs/spec/battle-engine-protocol.md and the terminology entries.
- 2026-08-19: user confirmed the reaction rule. No 'none' stance.
  A defender that cannot counter keeps dodge and defend.
