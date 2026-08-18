# Branch roadmap: issue 59, the battle engine contract

> Type: working—deleted at merge

## Change summary

The branch holds two documents and no code.

1. 'docs/spec/battle-engine-protocol.md', new. It is the contract
   of the battle engine: the process model, the transport, the
   error codes, sixteen commands, the types of the decide contract,
   and the evolution rule.
2. 'docs/reference/terminology-map.md'. It gets the term 'battle
   engine'. The entry 'operation history' gets the sentence that
   binds the term to the engine history.

## Call chain

No code changed. The document describes the calls that the later
issues implement:

- The client starts the process and sends 'hello'. The answer holds
  the protocol version and the command list.
- A battle starts with 'init' (the stage) and one 'place' for each
  ally unit. 'deploy_cells' gives the legal cells.
- A turn runs on 'actions' and 'reach' (the legal moves), then
  'reactions' (the reply of the defender to a planned strike), then
  'act' (the action and the reaction together).
- 'rollback' removes the last entry of the history. 'set_unit'
  writes values for a formula check.
- 'advice' asks the advisor. 'certify' asks for a guarantee.
- 'export' and 'load' carry a snapshot for a run log and a replay.

## Contention points

1. The engine holds the board. The 2026-08-17 note said that the
   engine holds no state and that every call carries a snapshot.
   Three behaviors of the 2026-08-19 discussion cannot run that
   way: 'rollback' needs a history, 'init' builds a session, and
   'set_unit' writes into a live board. The board therefore has one
   owner, and a client keeps no second copy. 'export' and 'load'
   keep the replay and the differential test.
2. The reaction list holds no 'none' stance. The user first asked
   for one: a defender that cannot reach the attacker cannot
   counter. #56 shows that the device menu holds no decline button,
   so the case is a list without counter entries, and dodge and
   defend stay. A strike that permits no reaction gives an empty
   list. The user confirmed this reading.
3. 'reactions' reads the attacker cell from the request. It does
   not read the current cell of the attacker. The client asks
   before it sends 'act', so the cell is the cell after a move that
   did not occur yet.
4. The contract declares 'act' and not 'step'. One concept keeps
   one name.
5. The shell that serves the contract left this branch. It is #69.
   The user ruled on 2026-08-19 that this issue ends at the
   contract.

## Verification

Documents only. The gates do not apply (CLAUDE.md, docs-only rule).
