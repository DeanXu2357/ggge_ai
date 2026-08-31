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
- The engine holds the operation history of the battle.
- 'init' plus the sequence of the commands that change the board
  reproduce the battle. The engine holds no other input.
- The Go package 'engine/battle' holds the contract: the board
  interfaces, the types that the interfaces speak, the dice and
  the sentinel errors. The types carry the JSON tags of the wire.
  They are 'Decision', 'BattleState', 'ActionsResponse',
  'ResponseAttacksResponse', 'BoardSummary' and the events. The
  interfaces hold the methods that a consumer calls: 'Act' and
  'Load' on 'BoardResolver'; 'Actions', 'ReachableCells',
  'ResponseAttacks', 'State' and 'Summary' on
  'BoardReader'. The contract imports no package of the engine.
  The package 'engine/protocol' holds the envelope, the codes,
  the command list and the per-command wrappers. It imports
  'engine/battle'. Below the contract the implementation is two
  kinds of package and one shell, and the imports run one way:
  the shell imports the systems; a writing system imports the
  contract 'engine/battle', the pure systems 'geometry' and
  'formula', and never another writing system (user ruling
  2026-08-30, issue #88).
- The contract types are the state. There is no separate
  definition package and no separate state package. 'battle.Unit'
  holds the id, the faction, the position, the size, HP, EN, SP
  and their maxima, the charges, the chance steps, the acted flag,
  the ammo, the debuffs, the skills, its 'battle.Mech' and its
  'battle.Pilot'; 'battle.BattleState' holds the bounds, the
  terrain, the phase, the turn and the units. The fields are
  exported and they carry the JSON tags of the wire. The contract
  holds no rule, only value helpers on its own fields
  ('Unit.Alive', 'Unit.Footprint', 'Weapon.Reaches',
  'BattleState.PhaseIndex', 'Footprint.Within'). 'BattleState.Clone' copies every field that
  a system writes and shares the weapons of a mech, which no code
  writes after the decode.
- The behavior systems are the only code that writes state during
  a battle. The writers of a field of a 'battle.BattleState' are
  'engagement/commit.go', 'turn/turn.go' and the board package
  ('Load', 'assemble', 'validate' and 'Clone'). Before the
  battle, the board fills the two values that a payload can leave
  out: a size of zero and an empty terrain.
  'engine/battle/engagement' resolves one activation:
  'engagement.Prepare(board, decision)' reads the board, judges
  every participant (the actor, the target, the weapon, the reach,
  the EN, the supporters, the bearer, the response) and returns
  every error of 'act' before the first write, or a 'Plan';
  'engagement.Commit(board, plan, dice)' writes the plan in order
  and cannot fail; 'engagement.Menu' answers 'response_attacks'
  through 'Prepare' with no response, so it refuses exactly what
  'act' refuses. 'engine/battle/turn'
  ('turn.Advance') rotates the phase, regenerates the EN, expires
  the debuffs and resets the acted flags. The
  pure system 'engine/battle/geometry' answers the distance, the
  reachable anchors and the occupied cells and writes nothing.
- The package 'engine/battle/board' is the shell. 'board.New'
  gives an empty board. 'Load' builds the content, assembles each
  unit and judges the result. It does this for 'init' and for
  'load' alike. It clones the content before it keeps it. A
  refused 'Load' leaves the board unchanged.
  It implements the contract, projects the answers of the read
  commands, and calls the systems. 'Act' is 'Prepare', 'Commit',
  'turn.Advance' in that order, so a refused 'act' leaves the
  board as it was; 'engine/server/handler' runs 'Act' on the
  board of the server and keeps no copy of it.
- The package 'engine/battle/formula' holds every formula of
  docs/reference/combat-formulas.md and every constant of the
  mechanism. It imports no package of the engine: a formula reads
  the input type 'formula.Side' and the values of the weapon, and
  no unit. 'engine/battle/engagement' is its only caller, and it
  adapts a unit and the weapon it fires into a 'Side' at each
  call.
- The package 'engine/server' holds the transport: the stdio loop,
  the command registry and the command 'hello'. The package
  'engine/server/handler' holds the body of every other command,
  the battle that the commands read and change, and the calls on
  the board. The handler parses every request: it reads
  'InitRequest' and passes the fields to the board. The server
  holds one board. 'main.go' injects it with 'board.New()', the
  one production import of the concrete package. The handler
  calls only the contract.
  No handler imports a system package. No package of
  'engine/battle' reads a type of 'engine/protocol'.

## Transport

- One JSON object on one line. This applies to a request and to a
  response.
- Request: 'id', 'cmd', 'payload'. A request that needs no field
  omits 'payload'. The transport of the engine reads an absent
  'payload' as an empty object, so every command takes such a
  request.
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
| illegal_action | The named action or response attack is not legal |

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

The field 'board' carries 'width', 'height', 'terrain' (the default
kind of the map) and 'terrain_cells' (the cells of another kind).
The section 'Terrain' holds the kinds.

An entry of 'victory' carries 'kind', one of 'destroy_all',
'destroy_target' and 'reach_cell', with the parameters of that kind.
The engine stores the list and reads no entry: the issue that judges
the end of a battle reads it.

The field 'events' is stored and not read: the issue that gives a
stage event its shape reads the table (user ruling 2026-08-27). The
field 'rules' is accepted and not read: the engine takes every rule
from a constant. The field 'seed' builds the session random source;
every server draw of the session reads that source.

The board opens at turn 1 in the ally phase with the enemies on it.
'place' is not implemented, so a battle with ally units starts
through 'load' today.

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

The cells are anchor cells: on each one, the whole footprint of the
unit stands on free cells of the board. The section 'Board
geometry' holds the rule.

The cells come in a deterministic order: the column first, the row
second. A client reads a list, not a set.

Refusals: no_session; illegal_action for an unknown unit id.

### actions

Purpose: what one unit carries.

Request: 'unit_id'. Response: 'unit', 'move_cells', 'weapons',
'map_weapons' and 'skills'.

The command reports. It selects nothing and it removes nothing. It
reads no target, no band and no resource: a weapon with no energy
left, and a weapon that reaches no unit from the cell of today,
stay in the list. The client draws the bands from these fields, the
user picks the move, the weapon and the target, and 'act' judges
the pick.

'unit' holds 'unit_id', 'faction', 'pos', 'size', 'hp', 'max_hp',
'en', 'en_max', 'move_range' and 'acted'.

'move_cells' holds the cells that 'reach' answers, in the same
order.

The answer holds two weapon lists. 'weapons' holds the direct
weapons and 'map_weapons' holds the area weapons. A weapon is in
one list or in the other, never in both.

A weapon entry holds 'name', 'range_min', 'range_max', 'en_cost',
'accuracy' and 'usable_after_move'. The entry carries no
ammunition: a direct weapon spends none. It carries no power: the
engine drops the power of a weapon when it reads the state.

A map weapon entry holds 'name', 'shape', 'origin',
'center_range', 'en_cost', 'ammo', 'accuracy', 'affects' and
'usable_after_move'. A null 'ammo' is a map weapon that spends no
ammunition. The section 'Types' holds the meaning of 'shape',
'origin' and 'affects'.

An entry of the two lists carries no weapon ability. The section
'Weapon abilities' holds the gap and the reason.

A skill entry holds 'kind', 'amount', 'uses', 'ends_activation',
'usable_after_move' and 'affects'. The entry carries no area: the
section 'Types' holds the reason. The field 'kind' is an open
string, not a value of the action kinds: the engine validates
nothing and resolves nothing until issue #81 closes the set. A
producer writes what it read.

Refusals: no_session; illegal_action for an unknown unit id;
illegal_state when the unit is destroyed, when the phase of the
unit is not the current phase, or when the unit acted.

### response_attacks

Purpose: the legal response attacks of one defender against one
planned strike.

The client calls this command before it sends 'act'. The attacker
chooses the action first. The client does not send that action yet.
The client asks for the response attacks of the defender, and it
sends the action and the response attack together in one 'act'.

Request:

| Field | Content |
|---|---|
| action | The action of the attacker |
| defender_id | The unit that takes the strike |

The engine reads the cell of 'move_to' of the action. The engine
does not read the current cell of the attacker. A client can
therefore ask about a move that did not occur. An action with no
'move_to' fires from the cell of today.

Response: 'defender' and 'attacker'.

'defender' holds 'unit_id', 'response_attacks',
'support_defenders' and 'support_attackers'. 'attacker' holds
'unit_id', 'support_defenders' and 'support_attackers'.

The list 'response_attacks' holds dodge, defend, one entry for
each weapon of the defender that counters, and 'none'. The stance
'none' is the unit that stands and takes the strike. The list holds
no 'shield': the shield of a unit settles during the damage, in
'act'.

A counter fires under the rule of an attack: the weapon reaches the
attacker, and the defender pays the EN. The list of the direct
weapons is the only source, so a map weapon enters no exchange. A
weapon carries no counter permission. A support strike needs a
support attack charge on top.

Only an action of the kind 'attack' asks the defender anything. A
map attack permits no response attack, and no other kind of action
reaches a unit, so the command refuses every other kind. A client
that runs one of them sends 'act' and no question.

A response attack entry holds the forecast 'incoming': what the
strike of the attacker does to the defender under that stance. A
counter entry also holds the forecast 'counter': what the counter
does to the attacker. A stance entry reads no support unit. A
support defender changes no outcome of the stance, so each one
carries its own forecast in 'support_defenders'.

A support defense entry holds 'unit_id' and the forecast
'incoming': what the strike does to that support defender. A support
attack entry holds 'unit_id', 'weapon' and the forecast 'strike':
what the shot of that unit does to its foe. The support attackers
of the defender fire at the attacker, and the support attackers of
the attacker fire at the defender.

A forecast holds 'hit_rate', 'damage' and 'kill'. 'damage' is the
conservative lower bound of the damage: no critical hit and no
bonus beside the debuffs the target carries. A weapon and a mech
that stack the critical rate to 100 percent are the one exception,
and the bound then holds the critical damage. 'kill' is true when
the bound is at least the hit points of the target. The hit roll is
no part of 'kill': a 'kill' of the dodge stance reads "the strike
destroys this unit when it lands".

A field that the engine cannot answer for that entry is null. Two
entries hold such a field. The entry of a support defender of the
defending side holds no 'hit_rate': the stance of the defender
settles that hit roll, so the rate stands beside the stance entry.
The entry of a support defender of the attacking side holds no
forecast at all: it takes the counter, and which weapon counters is
the pick of the defender.

The forecast of a support attack entry reads no stance of its foe,
because the foe picks the stance after this answer.

Refusals: no_session; bad_request when the action stands outside
the contract; illegal_action for an unknown unit id, a destroyed
unit, an action of a kind other than 'attack', a weapon the
attacker does not carry, and a weapon that does not reach the
defender from that cell.

### act

Purpose: run one action and write the result to the board.

Request:

| Field | Content |
|---|---|
| unit_id | The unit that acts |
| action | The action of the unit |
| response_attack | The response attack of the defender |
| dice | The dice input |

The field 'action' holds the move of the unit. The engine resolves
the move first and the action second; the section 'Unit payload,
action, and response attack' holds the rule.

The field 'response_attack' is necessary for an action of the kind
'attack', because such an action always gives a list. The field is
not permitted for every other kind. A response attack inside
'action' is a bad_request: the response attack travels in the field
'response_attack' of the request.

The client names every support unit of the engagement, and the
engine names none. The action holds 'support_attackers', the units
of the side of the actor that join the strike, and
'support_defender', the unit that takes a counter strike for the
actor. The response attack holds the same two fields for the
defending side: 'support_attackers' join the answer of the
defender, and 'support_defender' is the unit that takes the strike
in place of the defender. Each list holds the unit ids that
'response_attacks' reports, and no unit two times.

A defender that defends takes the strike itself and names no
support defender. A defender that carries a shield defends with the
shield: the response attack menu offers no shield stance, so the
shield multiplier applies to the defend stance of that unit.
Whether the game pairs a support defender with the stand is not
measured; the engine permits it.

The rules cap the number of support attackers of one strike. A unit
that the engagement destroys or drains before its own shot fires
nothing.

The field 'dice' holds 'mode'. The value 'forced' is the manual
roll: it also holds 'outcomes', a list of the labels 'hit' and
'miss', and the engine reads one label for each chance event, in
the resolution order. The list must hold one label for each chance
event that the action can reach: one for the support attack of the
attacker when the request names one, one for the strike, one for
the support attack of the defender when the response attack names
one, and one for the counter when the response attack names one.
The engine counts them before the first write, with every unit
alive, so a list that a kill would have made long enough is refused
as well. A label past the last chance event is not
read. The value 'sampled' is the server draw: the
engine draws from the session random source, one draw for each
chance event. One volley of support attackers is one chance event
until issue #47 gives each supporter a draw.

Response: 'events' and 'board'.

'events' is the resolution in order. An entry carries 'event'. The
value 'strike' carries 'strike' (support, strike, defender_support,
or counter), 'shooter_id', 'struck_id', 'weapon', 'landed',
'damage', and 'killed'. The value 'phase' carries 'turn' and
'phase': the engine rotated the phase after the activation, and
the section 'Turn cycle' holds the rule.

'board' is the summary: 'turn', 'phase', 'pending' (the ids of the
units of the phase that can still act), and 'gone' (the sides
'ally' and 'enemy' with no living unit, in that order). The engine
judges no end of the battle: a board with one side gone answers
like any other, and the client stops on 'gone' (user ruling
2026-08-27).

The command runs on a copy of the board and installs the copy when
the whole run succeeds. A refusal changes no board and moves the
session random source nowhere. A success writes one entry to the
operation history.

The command judges the pick against the rules of the mechanism, and
not against a list of actions: the reporting commands read the same
rules, so a pick that the report offers passes here. A refusal
leaves the board as it was.

The command resolves no action of the kind 'map_attack'. The
contract holds the shape of a map weapon from version 1.8, but no
rule reads it: nothing expands a shape into cells, nothing turns a
shape, nothing spends the ammunition, and nothing picks the units
of the area. The engine refuses the kind until these rules land
(issue #79).

The command resolves no skill either. A skill starts no engagement,
and the contract holds no shape for what a skill does. The user
ruled on 2026-08-26 that the game gives skills that raise the damage
of the caster, that cut the damage it takes for one turn, and that
force an evasion in the next engagement. None of the three is a
restore of hit points or of energy, and each carries a duration that
no field of the contract holds. Issue #81 settles the shape.

The value set of 'kind' holds no skill for the same reason. What a
skill does is not a kind of action, and the two values 'skill_heal'
and 'skill_en_refill' put an effect in that set. They are gone, so
no action of the contract uses a skill today, and 'act' refuses one
with the message of an unknown kind. The state still carries the
skill list of a unit: what a unit holds is not the same question as
what a skill does.

Refusals: no_session; illegal_state when the phase of the unit is
not the current phase, or when the unit acted in this turn;
illegal_action for a target that is no foe, a weapon the unit does
not carry, a weapon the unit cannot pay for, a weapon that does not
reach the target, a support unit that cannot join or intercept, a
support attacker list above the cap of the rules, a response
attack that breaks a rule of the stance, an absent necessary
response attack, an action that carries 'move_to' when its weapon
or its skill holds 'usable_after_move' false, and an anchor that
the unit does not reach; bad_request when an 'outcomes' label
stands outside 'hit' and 'miss', and when the 'outcomes' list holds
fewer labels than the chance events the action can reach.

### export and load

Purpose: the snapshot of the session, for a run log, a replay, and
a differential test.

'export' takes no field and gives 'state', 'history', 'seed', and
'gone'. 'load' takes 'state', 'history', and 'seed', and replaces
the session. An entry of 'history' carries 'cmd' and 'payload', the
request of one command that changed the board: 'act' and 'place'
write such an entry. 'seed' is optional on 'load'; an absent seed is
0. 'load' builds the session random source at the start of its
stream: a loaded history is a record, not a replay.

'gone' names the sides 'ally' and 'enemy' with no living unit, in
that order. It is the field of the board summary of 'act', so a
client that resumes a session reads the end of the battle from
'export' alone.

'export' gives back the 'pending_events' and the 'fired_events' of
the loaded state. The engine reads neither list today, and it holds
them unread so that a snapshot survives a load and an export.

The state carries 'phase'. A state without that field is a
bad_request. 'load' judges the units against the bounds, and a
unit that stands outside the board is a bad_request.

## Turn cycle

The phases of one turn run in the order ally, third_party, enemy.
A unit is pending when it lives, is of the faction of the phase,
and did not act in this phase.

After one activation, while the faction of the phase holds no
pending unit, the phase moves to the next entry of the order. The
move from the enemy phase to the ally phase adds one to the turn.
A board with no living unit keeps its phase.

Every move opens the phase of one faction. At that phase start:

- Every living unit of the faction gets its activation back.
- Every living unit of the faction regenerates one tenth of its
  maximum EN, floored, and the EN does not pass the maximum
  (docs/reference/combat-formulas.md line 191). The floor is a
  hypothesis: the reference leaves the rounding open at line 310,
  and the user ruled on 2026-08-27 to floor until a device
  measurement settles it.
- Every living unit of every faction drops the debuffs that one
  full round has passed: a debuff hung in the phase of index p is
  gone when the phase of index p + 3 opens
  (docs/reference/combat-formulas.md line 269). The phase index is
  turn times 3 plus the position of the phase in the order.

The phase start resets no chance step and no support charge, and
fires no stage event. The three wait for the issue that gives them
a shape (user ruling 2026-08-27).

## Board geometry

A cell is a pair of integers: the column first, the row second.

A unit covers a rectangle of cells. This rectangle is the
footprint. The field 'size' holds the width and the height of the
footprint, in the axis order of a cell. The field 'pos' holds the
anchor cell: the cell of the footprint with the least value on each
axis. A unit does not turn. A footprint of 2 by 3 stays 2 by 3, and
the board decides which units carry which size.

A payload that carries no 'size' gives the unit one cell.

A unit moves on the four orthogonal steps. One step costs one point
of the move range. A diagonal cell costs two steps. Range reads the
same steps.

The distance between two units is the least distance between a cell
of the one footprint and a cell of the other footprint. Two
footprints that touch are at distance 1. Two footprints that share
a cell are at distance 0. Two units of one cell give the distance
of the two cells.

Every range answer reads this distance: the band of a weapon and
the move range that lets a support unit join. A weapon with a
'range_min' of 2 does not fire at a foe that touches the
footprint, because that foe is at distance 1.

A unit moves as one body. Each step of the path carries the whole
footprint. An anchor is a destination only when every cell of the
footprint is on the board and holds no other unit. A cell of an
enemy or of a third party stops the path. A cell of an ally lets
the path through and is no destination.

The Python side holds no geometry of its own. It carried the
eight king steps and one cell for every unit, and it retired with
the rest of the Python rules (issue #73). A golden case that the
Python side wrote therefore compares no result that reads the
distance or the footprint, and a golden case that compares a
response attack list holds units of one cell in one row. The
'actions' command left the comparison with issue 63: it reports
what one unit carries, and the Python side holds no such answer.

## Types

### Unit payload, action, and response attack

The authority for these three schemas is the Go package
'engine/battle'. 'src/ggge_ai/engine/state.py' holds the same
structs in Python and 'src/ggge_ai/engine/codec.py' writes the
wire form from them. The contract names the payload of one
activation 'action'; the struct names the same thing 'Decision'.
The Go type keeps the struct name, and the wire field keeps the
contract name.
The enum of the kinds of one action is 'ActionKind' on both sides.
The enum holds no kind of movement. Its wire field is 'kind', and
its value set is frozen.

The resolution order of one activation: the move first, then the
action. The move is the field 'move_to' of the action. Every effect
that reads a cell reads the cell after the move. There is no
exception to this order.

An action does not always carry a move. The permission is the field
'usable_after_move' of the weapon of the action, or of its skill.
A true value permits a move in the same activation; a false value
makes the action pre-move only. The permission is a property of
that weapon or that skill, not of the kind of the action: a map
weapon is a common holder of a false value, but some map weapons
fire after a move, and some skills of the source 'pilot' or 'crew'
hold a false value (user ruling 2026-08-20).

A skill carries no area on the wire. The area of a skill is an
arbitrary set of cells. It takes any shape, for example the shape
of the letters "ILOVEU". A minimum range, a maximum range and a
radius cannot express such a shape, so they are the wrong
description of the area and not an incomplete one (user ruling
2026-08-31). The representation of the area is not decided, and a
later issue decides it. The center travels in the field 'aim' of
the action, and a single target travels in the field 'target_id'.

The field 'affects' holds the faction filter of the units that a
skill acts on: 'ally', 'enemy', or 'all'. The value set holds no
'self'. A skill that acts on the caster alone carries an 'affects'
of 'ally', because the caster is an ally in its own cell.

The fields 'pos' and 'size' of a unit hold its footprint. The
section 'Board geometry' holds their meaning.

The rules of the wire form:

- A cell is a JSON pair, in the order of the Python tuple.
- The center of an area effect is on the wire, in the field 'aim'.
  The engine does not derive the center from the cell of the actor.
- Every field of the type is on the wire. A field that holds no
  value is null.
- A field with three values keeps its three values: 'hit' is true,
  false, or null. Null says that the caller settles that node
  somewhere else.
- The stance 'none' is on the wire: it is the unit that stands and
  takes the strike. The stance 'shield' is not. A payload that
  carries 'shield' is a decode error.
- A decode and an encode of one payload give the same bytes a
  second time.
- The trigger and the effect of a stage event stay free objects.
  The issue that runs the event table reads them.

A field that 'engine/state.py' holds and the Go struct does not is
a test failure: 'tests/test_engine_codec.py' compares the fields of
the dataclass with the JSON tags of the Go struct.

The Go struct can hold a field that 'engine/state.py' does not.
Such a field carries a rule that the Python side never held. It is
optional on the wire: a payload that omits it keeps the behavior of
the build before the field. The test names each one in
'ENGINE_ONLY', so a Go field that nobody declared is still a test
failure.

### The two weapon types

A weapon is a direct weapon or a map weapon. The two are separate
types, and a mech holds them in two lists: 'weapons' and
'map_weapons'.

A direct weapon strikes one unit. It carries a band, 'range_min'
and 'range_max', and an exchange resolves it. A direct weapon
spends no ammunition, so it carries no ammunition field.

A map weapon strikes every unit of an area. It starts no exchange,
and it grants no response attack. Version 1.8 gives the map weapon
its fields. It gives no rule: no rule expands a shape, turns a
shape, spends the ammunition, picks the units of the area, or
computes the damage. Issue #79 writes those rules.

'ShapeRange' is the area. It holds 'cells', a list of cell offsets
from an origin, and 'direction'. The author writes the offsets one
time, against one base heading. The direction then turns the full
set of the offsets. The rotation is a rule, and version 1.8 holds
no rule, so no code turns a shape yet.

'Direction' holds 'none', 'up', 'down', 'left' and 'right'. The
value 'none' is a shape that needs no heading, for example a shape
that is the same in every heading.

'MapWeaponOrigin' tells where the offsets start. 'self' opens the
shape at the cell of the caster. 'cell' opens it at a cell that the
player picks; the picked cell travels in the field 'aim' of the
action. The field 'center_range' bounds how far the picked cell can
sit from the caster, and it carries a meaning only when 'origin' is
'cell'.

'MapWeaponAffects' holds the faction filter of the units that the
area strikes: 'ally', 'enemy', or 'all'. It is a separate enum from
'SkillAffects', because the audience of a map weapon and the
audience of a skill are two different sets (user ruling
2026-08-31).

The field 'ammo_max' of a map weapon is the static maximum. The
field 'ammo' of a unit is the count that is left, keyed by the name
of the weapon. The maximum belongs to the definition, and the count
belongs to the state.

The producer of a map weapon can leave the shape empty. The panel
of the game shows no cells, no heading and no origin, so the vision
layer of this repository writes an empty 'cells', a 'direction' of
'none' and an 'origin' of 'self'. An empty shape is data that is
missing, and not an area of no cells.

### The unit, the pilot and the mech

A unit is a pilot that rides a mech, on the board of one stage. The
payload keeps the three apart (user ruling 2026-08-28).

The unit is the current state of the pairing. It records state and
the maxima of state, and it takes no part in a computation:

| Field | Content |
|---|---|
| hp, max_hp | The hit points now, and their maximum |
| en, en_max | The energy now, and its maximum |
| sp, sp_max | The skill points of the pilot now, and their maximum |
| pos, size, acted, the charge counters, ammo, debuffs, skills | The board state, as before |
| pilot | The pilot, as data |
| mech | The mech, as data |

The unit carries no attack, no defense, no mobility, no movement
range and no weapon list of its own. A rule that needs one of them
reads the pilot or the mech.

The three maxima 'support_attack_charges_max',
'support_defend_charges_max' and 'chance_steps_max' are state of
the unit, and the pilot decides them: an ability of the pilot whose
condition matches the mech (its role, its tags or its series) raises
the count (user ruling 2026-08-28). No code derives them yet; a
payload carries them as given. The pairing conditions belong to
issue #72 and the derivation to issue #77.

The pilot holds the values of the game's pilot panel:

| Field | Content |
|---|---|
| ranged | 射擊值 |
| melee | 格鬥值 |
| awaken | 覺醒值 |
| defense | 守備值 |
| reaction | 反應值 |
| sp | The skill point pool |

The mech holds its own values:

| Field | Content |
|---|---|
| hp, en | The hit points and the energy of the mech |
| attack, defense, mobility | The three combat values of the mech |
| move_range | The movement range of the mech |
| weapons | The direct weapons of the mech, in the weapon payload |
| map_weapons | The map weapons of the mech, in the map weapon payload |

A weapon carries 'categories', a list over 'ranged', 'melee' and
'awaken', null when the producer knows no category. The pilot
attack of a strike is the highest pilot value among the categories
of the weapon; a weapon with no category reads the highest of the
three (user ruling 2026-08-28). Go: 'WeaponCategory',
'Pilot.AttackFor'.

At 'init', a unit whose 'max_hp' or 'en_max' is 0 takes the value
of its mech, and a unit whose 'sp_max' is 0 takes the 'sp' of its
pilot. An explicit value stays. The abilities of the pilot and of
the mech do not enter the maxima yet; issue #77 owns that
derivation. The datamine holds no SP pool for a pilot; the device
is its source.

This section replaces the reading of 2026-08-21 that the unit
carries a stored final panel that every rule reads. That reading
is retired (docs/record/decisions.md, 0828).

### Terrain

Terrain belongs to a cell. The five kinds are 'space',
'atmospheric', 'ground', 'surface' and 'underwater'. One stage map
can hold more than one kind.

The state carries the terrain of the map in two optional fields:

| Field | Content |
|---|---|
| terrain | The kind that every cell of the map takes |
| terrain_cells | The cells that take another kind |

Each entry of 'terrain_cells' holds 'cell' and 'terrain'. A state
with no 'terrain' puts the whole map in space. A terrain name
outside the five is a decode error.

No rule of the engine reads the terrain today. The state carries
the terrain of each cell so that the rule has its data when it
lands. What reads it is a weapon ability, and the section 'Weapon
abilities' holds that gap.

There is no rules payload. Every rule of the mechanism is a
constant of 'engine/battle/formula/rules.go', and the section 'Weapon
abilities' holds the rule that does vary. One stage held one terrain
value until 2026-08-26.

The field 'board' of 'init' carries the terrain of the map:
'terrain' is the default kind, and 'terrain_cells' lists the cells
of another kind. The section 'init' holds the request.

### Weapon abilities

A weapon ability is one named ability of one weapon, positive or
negative. The user ruled on 2026-08-26 that the effects the engine
missed are abilities of a weapon, and not rules of the board:

- '對水中目標傷害減半' divides the damage of that weapon when the
  cell of the target holds the terrain 'underwater'. It reads the
  cell of the target.
- '攻方自身在水中時不可使用' forbids the weapon while the cell of
  the attacker holds that terrain. It reads the cell of the
  attacker.
- A map weapon fires before the move and ends the activation of
  the unit. An ability lifts the first half.

The engine models a closed set of ability kinds. A weapon that
carries a kind outside the set resolves as a weapon with no
ability: the damage divides by 1 and the weapon fires. A new
ability of the game adds a kind to the set. It never adds a field
to the weapon entry, because the abilities of the game are open
and the fields of a contract are not.

The wire carries no ability today, and no ability kind is modelled.
Issue #80 builds the model and adds the field of the weapon entry
that holds the list. Until then the board passes 1 for the terrain
correction of every weapon
('strikeDamage' in 'engine/battle/engagement/strike.go').

### Differential cases

'tests/fixtures/engine/' holds the cases. Python writes them, and
the Go tests in 'engine/differential' read the same file and
compare. One case file holds:

| Field | Content |
|---|---|
| name | The name of the case, equal to the file name |
| note | What the board carries |
| setup | The event table and the board |
| checks | The list of the checks |

Each check names an 'op', its 'input', and the 'expect' that the
Python side produced while it still held the rules of the battle.
The block 'rules' of the setup and the check 'rules' that read it
are deleted: the engine takes no rule from outside, so a value in a
file could only disagree with the constant that the engine uses. An op that the
Go build does not implement is skipped, not failed, so a port issue
finds its checks waiting. The files are frozen: the writer retired
with the Python rules (issue #73), and no process writes them
again. A case that the engine must not keep is deleted, never
regenerated. A change of the contract moves the files to the new
shape in place. It moves the fields and it changes no expectation,
because a regeneration is not available.

A case can also be written by hand from the reference documents.
Its 'note' says so and names the document lines that give each
expectation. The two turn-cycle cases are of this kind.

Float comparison: the two sides compare with a relative tolerance
of 1e-9 and an absolute floor of 1e-12. A number that one side
copies from the other matches bit for bit, because both write the
shortest decimal that reads back as the same double. A number that
each side computes does not: the two runtimes call different libm
code for 'exp', and the results part in the last bits. The
tolerance hides no wrong formula, because a wrong formula misses by
far more, and it hides no wrong integer, because the smallest
difference between two integers is 1.

## Evolution

- A change adds a field. A change does not give a new meaning to a
  field that exists.
- A change that adds a field raises the protocol version.
- 'hello' gives the version and the command list. A client reads
  them before it sends a command that it does not know to be
  implemented.
- One exception on record: version 1.4 (2026-08-28, issue #84)
  removed the flat value fields of the unit payload and put the
  nested objects 'pilot' and 'mech' in their place, on a user
  ruling that the unit records state and takes no part in a
  computation. A client of version 1.3 does not read a 1.4 unit.
  The section "The unit, the pilot and the mech" holds the shape.
- A second exception on record: version 1.5 (2026-08-30, issue #88)
  removed 'can_counter' from the weapon of the state and from the
  weapon entry of 'actions', on a user ruling that the game grants
  no counter permission to a weapon. A counter fires under the rule
  of an attack. A client of version 1.4 reads a 1.5 weapon, and it
  reads no counter permission.
- A third exception on record: version 1.6 (2026-08-31, issue #88)
  removed the field 'error' from the answer of 'actions'. The
  command now refuses a unit that acted with the code
  'illegal_state'. The code 'already_acted' is retired. The same
  change moved the contract types from 'engine/protocol' to
  'engine/battle'. The same version also dropped the commands
  'rollback', 'set_unit', 'advice' and 'certify', with their request
  and response types, the goal and the budget parameters, the verdict
  and the guarantee: no build implements them, and the issue that
  implements one declares it again. The unused chance-event types left
  the contract with them. The JSON stays the same everywhere else.
- A fourth exception on record: version 1.7 (2026-08-31, issue #88)
  removed 'range_min', 'range_max' and 'blast' from the skill of the
  state and from the skill entry of 'actions', on a user ruling that
  the area of a skill is an arbitrary set of cells that these three
  fields cannot express. A skill carries no area on the wire, and the
  representation of the area is not decided. A client of version 1.6
  reads a 1.7 skill, and it reads no area.
- A fifth exception on record: version 1.8 (2026-08-31, issue #88)
  split the weapon into two types. 'Weapon' is a direct weapon and
  'MapWeapon' is an area weapon. The field 'map_weapon' of the
  weapon is removed, and the field 'ammo' of the weapon entry of
  'actions' is removed with it: a direct weapon spends no
  ammunition. A mech carries the new list 'map_weapons' beside
  'weapons', and the answer of 'actions' carries the new list
  'map_weapons' beside 'weapons'. The wire loses no information: a
  map weapon moves from one list to the other. The new type
  'ShapeRange' holds the area, with the new enums 'Direction',
  'MapWeaponOrigin' and 'MapWeaponAffects'. This version defines the
  shape and it fires no map weapon: no rule reads the new fields.
  A client of version 1.7 does not read a 1.8 weapon list.
