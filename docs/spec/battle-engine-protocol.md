# Battle engine protocol

> Type: spec—the authoritative description of an implemented mechanism or format

The battle engine is one Go process. It holds the board of one
battle. It answers commands on stdin and stdout. This document is
the contract between the engine and its clients.

The engine holds no game logic in this document. The commands that
carry the rules are declared here and are implemented by the later
issues of the port (#60 to #68).

## Process model

- One process holds one battle. A client that must run two
  battles starts two processes.
- The engine is the authority for the board. A client keeps no
  second copy of the board.
- The engine holds the operation history of the battle. The
  command 'rollback' removes the last entry.
- 'init' plus the sequence of the commands that change the board
  reproduce the battle. The engine holds no other input.

## Transport

- One JSON object on one line. This applies to a request and to a
  response.
- Request: 'id', 'cmd', 'payload'.
- Response, success: 'id', 'ok' true, 'payload'.
- Response, failure: 'id', 'ok' false, 'error' with 'code' and
  'message'.
- The 'id' of a response is equal to the 'id' of its request.
- The engine answers one request with one response. The engine
  sends no unsolicited message.
- EOF on stdin stops the process with status 0.

Error codes:

| Code | Meaning |
|---|---|
| unknown_command | The engine does not know the command name |
| not_implemented | The command is declared, but its issue is not merged |
| bad_request | The payload does not match the schema |
| no_session | The command needs a board, and 'init' did not run |
| illegal_state | The board does not permit the command now |
| illegal_action | The named action or reaction is not legal |
| empty_history | 'rollback' found no entry |

An error response does not stop the process. An error response does
not change the board.

## Commands

### hello

Purpose: the version and the command list of the build.

Request: no fields. Response: 'protocol', 'commands'. Each entry of
'commands' carries 'name' and 'implemented'.

### ping

Purpose: a liveness check. Request and response carry no fields.

### init

Purpose: build the board of one battle.

Request:

| Field | Content |
|---|---|
| board | The width and the height |
| enemies | The enemy units, with their cells |
| victory | The victory conditions of the stage |
| events | The stage event table |
| deploy_cells | The cells that accept an ally unit |
| rules | The rule overrides of the stage |
| seed | The seed of the session random source |

Response: 'turn', 'phase', 'deploy_open'.

'init' on a live session replaces the battle. The history starts
again.

Refusals: bad_request.

### deploy_cells

Purpose: the cells that accept an ally unit now.

Request: no fields. Response: 'cells'.

Refusals: no_session; illegal_state when the deploy phase is over.

### place

Purpose: put one ally unit on the board.

Request: 'unit' (the full unit payload) and 'cell'.
Response: 'placed' (the unit ids on the board) and 'cells' (the
cells that still accept a unit).

Refusals: no_session; illegal_state when the deploy phase is over;
illegal_action when the cell is not a deploy cell, when the cell
holds a unit, or when the unit id is on the board.

### roster

Purpose: the current state of every unit, both factions.

Request: no fields. Response: 'units'.

Refusals: no_session.

### reach

Purpose: the cells that one unit can move to.

Request: 'unit_id'. Response: 'cells'.

Refusals: no_session; illegal_action for an unknown unit id.

### actions

Purpose: the legal actions of one unit.

Request: 'unit_id'. Response: 'actions'.

Refusals: no_session; illegal_state when the phase of the unit is
not the current phase; illegal_state when the unit acted in this
turn.

### reactions

Purpose: the legal reactions of one defender against one planned
strike.

The client calls this command before it sends 'act'. The attacker
chooses the action first. The client does not send that action yet.
The client asks for the reactions of the defender, and it sends the
action and the reaction together in one 'act'.

Request:

| Field | Content |
|---|---|
| defender_id | The unit that takes the strike |
| attacker_id | The unit that makes the strike |
| attacker_cell | The cell of the attacker after its move |
| weapon_id | The weapon of the strike |

The engine reads 'attacker_cell' from the request. The engine does
not read the current cell of the attacker. A client can therefore
ask about a move that did not occur.

Response: 'reactions'. An empty list means that the strike permits
no reaction.

Refusals: no_session; illegal_action when the weapon does not reach
the defender from that cell.

### act

Purpose: run one action and write the result to the board.

Request:

| Field | Content |
|---|---|
| unit_id | The unit that acts |
| action | The action of the unit |
| reaction | The reaction of the defender |
| dice | The dice input |

The field 'reaction' is necessary when 'reactions' gives a list
that is not empty for this strike. The field is not permitted when
that list is empty.

The field 'dice' holds 'mode'. The value 'forced' also holds
'outcomes': the engine reads one outcome for each chance event, in
the resolution order. The value 'sampled' holds no outcome: the
engine draws from the session random source of 'init'.

Response: 'events' (the resolution in order) and 'board' (the new
summary).

Refusals: no_session; illegal_state when the phase of the unit is
not the current phase, or when the unit acted in this turn;
illegal_action for an action that 'actions' does not give, for a
reaction that 'reactions' does not give, for an absent necessary
reaction, or for a short 'outcomes' list.

### rollback

Purpose: remove the last entry of the operation history.

'rollback' removes the last command that changed the board. The
commands 'act', 'place', and 'set_unit' write such an entry.

Request: no fields. Response: 'undone' (the command name and its
payload) and 'board'.

Refusals: no_session; empty_history.

### set_unit

Purpose: write values into one unit, without the turn rules.

This command serves a formula check: an operator sets the values
that the device shows, and then runs one engagement.

Request: 'unit_id' and 'fields' (the values to change: the cell,
the HP, the EN, the weapons, the unit values, the pilot values, the
debuffs).

Response: 'unit'.

Refusals: no_session; illegal_action for an unknown unit id, or
for a cell that holds another unit.

### advice

Purpose: the decision of the advisor for one faction.

Request: 'faction', 'budget', 'algo', and 'goal'. The field 'goal'
is optional: the engine uses the victory conditions of 'init' when
the request holds no goal.

Response: a 'Verdict'.

The engine answers when the faction holds a decision that waits.
An ally reaction against an enemy strike is such a decision, and
the phase of that moment is the enemy phase. The gate is the
decision, not the phase.

Refusals: no_session; illegal_state when the faction holds no
decision that waits.

### certify

Purpose: the guarantee of one action.

Request: 'action'. Response: 'guarantee'.

### export and load

Purpose: the snapshot of the session, for a run log, a replay, and
a differential test.

'export' takes no field and gives 'state' and 'history'. 'load'
takes the same two fields and replaces the session.

## Types

### Verdict

| Field | Content |
|---|---|
| action | The chosen action, or the chosen sequence of one turn |
| expected_value | The value of the chosen action |
| guarantee | KILL or NONE |
| diagnostics | The statistics of the search |

A 'guarantee' of NONE says that the engine holds no certificate. It
does not say that the action fails.

### Goal parameters

| Field | Content |
|---|---|
| victory | destroy_all, destroy_target, or reach_cell, with its parameters |
| score | The score constraints: the survival of every unit, and the HP limit |

The goal selects the statistic of the leaf evaluation.

### Budget

| Field | Content |
|---|---|
| time_ms | The limit in milliseconds |
| nodes | The limit in nodes |

An exhausted budget gives the best action of that moment. The
diagnostics record the exhaustion.

### Unit payload, action, and reaction

The authority for these three schemas is 'src/ggge_ai/sandbox/
model.py'. Issue #60 lands them in the engine.

## Evolution

- A change adds a field. A change does not give a new meaning to a
  field that exists.
- A change that adds a field raises the protocol version.
- 'hello' gives the version and the command list. A client reads
  them before it sends a command that it does not know to be
  implemented.
