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
  data packages, two kinds of system package and one shell, and
  the imports run one way: the shell imports the systems; a
  system imports the two data packages 'engine/battle/state' and
  'engine/battle/def', the contract 'engine/battle' and the pure
  systems 'geometry' and 'formula', and never another writing
  system (user ruling 2026-08-30, issue #88).
- Three layers hold the data of a battle. The contract
  'engine/battle' holds the wire form. 'battle.Unit' holds the
  faction, the position, the size, HP, EN, SP and their
  maxima, the charges, the chance steps, the acted flag, the map
  weapon ammunition, the debuffs, the skills, its 'battle.Mech' and its
  'battle.Pilot'; 'battle.BattleState' holds the bounds, the
  terrain, the phase, the turn and the units. The fields are
  exported and they carry the JSON tags of the wire. A consumer of
  the contract reads these types, and no other form of the data
  leaves the engine.
- 'engine/battle/def' holds the data of a battle that no rule
  writes: 'Mech', 'Pilot', 'Weapon', 'MapWeapon', 'Skill',
  'AffectArea' and 'ShapeRange'. They are distinct structs with
  exported fields and no JSON tag. 'MapWeapon' and 'Skill' each
  embed 'AffectArea', as they do in the contract.
  The package declares no vocabulary of its own: it
  reads 'Cell', 'Direction', 'WeaponCategory', 'MapWeaponAffects'
  and the skill enums from the contract. A unit points at its mech
  and at its pilot, so every copy of a battle shares them.
- 'engine/battle/state' holds the data of a battle in two stored
  halves and one view. 'state.Content' holds the invariants:
  'Units []UnitContent' and the bounds, the terrain and the terrain
  cells. 'state.UnitContent' holds the faction, the size, the six
  maxima, the shield flag, the support defense flag and the two
  pointers into 'def'. 'state.Values' holds the variables: 'Units
  []UnitValue', index-aligned with the content units, plus the phase
  and the turn. 'state.UnitValue' holds the position, HP, EN, SP,
  the acted flag, the chance steps, the two charge counts, the
  skills, the map weapon ammunition and the debuffs. 'state.Battle'
  is the view: two pointers, 'Content *Content' and 'Values
  *Values', and no data of its own. No type joins a content field
  and a value field in one struct (user ruling 2026-09-02).
  'state.Unit' is the handle of one unit: the embedded pointer
  '*UnitContent' and the pointer 'Value *UnitValue'. 'Battle.Units'
  walks the handles with their ids, and 'Battle.UnitAt' is the door
  for an id from the wire. The placement rule: 'UnitValue' holds
  every field that a rule of a battle writes, plus the three pools a
  unit spends ('SP', 'MapWeaponAmmo' and 'Skills'); a maximum is the
  bound of a pool and not a pool, so it stands for the whole battle
  and sits in the content. A rule reads and writes 'unit.Value.HP',
  never 'unit.HP' (user ruling 2026-08-31).
- 'Values.Clone()' answers the working column of a writer. It
  deep-copies the slices of each value ('Skills' with their amounts,
  'MapWeaponAmmo' and 'Debuffs'), so a writer never reaches the
  column it received. A reader clones nothing: it reads the view
  over the columns of the board.
- The conversion between the wire form and the engine form runs at
  two points and nowhere else: 'state.FromContract' inside
  'board.Load', and 'state.Battle.ToContract' inside 'board.State'.
  'FromContract' answers the pair. 'board.State' converts the view.
  A loaded board shares nothing writable with its payload, and the
  answer of 'State' shares nothing writable with the board. The
  definition data is shared; no code writes it after the decode.
- No layer holds a rule. Each layer holds value helpers that read
  the fields of their own struct and decide nothing about the
  battle. The contract holds 'Unit.Footprint', 'Footprint.Within',
  'Footprint.Cells', 'Cell.Before' and 'Faction.Opposing'. The state
  package holds 'Unit.Alive', 'Unit.Footprint', 'Unit.WeaponAt',
  'Battle.Units', 'Battle.UnitAt', 'Values.Clone' and
  'Values.PhaseIndex'. The definition package holds 'Weapon.Reaches'
  and 'Weapon.Debuff'.
- The behavior systems are the only code that writes the state of a
  battle. Each one is a pure computation over the view: it clones
  the values column at its entry, writes the clone through a view
  over the same content, and answers the clone as the new values
  column (user ruling 2026-09-01, issue #91). The content column is
  never written: the test 'TestAnActLeavesTheContentColumnAsItWas'
  and every golden 'apply' check compare the content before and
  after an act. Neither system depends on the other. The writers of
  a value are 'engagement/commit.go' and 'turn/turn.go'. Before the battle,
  'board.Load' works on the wire form: 'assemble' fills a maximum
  that the payload leaves at zero, and 'validate' fills the two
  values that a payload can leave out, a size of zero and an empty
  terrain. 'engine/battle/engagement' resolves one activation, and
  it exports one entry for the write: 'engagement.Commit(board,
  decision, dice)' answers the values column that the
  activation leaves, or an error. Three steps run inside the
  package. The prepare phase reads the board, judges every
  participant (the actor, the target, the weapon, the reach, the EN,
  the supporters, the bearer, the response) and returns every error
  of 'act' before the first write, or a plan. The dice coverage
  check reads the draws of that plan. The write phase writes the
  plan in order and cannot fail. 'engagement.Menu(board, decision,
  defenderID)' answers 'response_attacks' through the same prepare
  phase with no response, so it refuses exactly what 'act' refuses.
  'engine/battle/turn' holds 'turn.Advance(board)': it rotates the
  phase, regenerates the EN, expires the debuffs and resets the
  acted flags, and it answers the new values column with its
  rotations. 'Advance' runs for any view, and it needs no prior
  engagement. The pure system
  'engine/battle/geometry' answers the distance, the reachable
  anchors and the occupied cells and writes nothing.
- The package 'engine/battle/board' is the shell. It stores the
  pair: the content and the values. 'board.New' gives an empty
  board. 'Load' takes the wire form, assembles each unit, judges the
  result and converts it into the pair. It does this for 'init' and
  for 'load' alike. A refused 'Load' leaves the board unchanged. It
  implements the contract, projects the answers of the read
  commands, and calls the systems. A read command hands the systems
  the view over the columns of the board. 'Act' is four steps:
  'engagement.Commit' on that view; 'turn.Advance' on a view over
  the content and the column that step one answered; one assignment
  of the final column to the board; the typed 'battle.ActResult'
  with the strikes and the rotations. A refused 'act' returns before
  that assignment, so it leaves the board as it was;
  'engine/server/handler' runs 'Act' on the board of the server,
  flattens the result into the event list of the wire, and keeps no
  copy of the board.
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
The parameter 'target_id' of 'destroy_target' is a position in the
list 'enemies' of this request. The engine stores the list and reads no entry: the issue that judges
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
illegal_action when the cell is not a deploy cell, or when the cell
holds a unit.

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

A map weapon entry holds 'name', 'apply_shape', 'effect_shape',
'en_cost', 'ammo', 'accuracy', 'affects' and 'usable_after_move'.
'ammo' is the count that is left: the entry at position i reads
'map_weapon_ammo[i]' of the unit. Whether a map weapon spends
ammunition at all is a fact of its definition, in 'ammo_max', and
not of the count. The section
'Types' holds the meaning of the two shapes and of 'affects'.

An entry of the two lists carries no weapon ability. The section
'Weapon abilities' holds the gap and the reason.

A skill entry holds 'kind', 'amount', 'uses', 'ends_activation',
'usable_after_move', 'apply_shape', 'effect_shape' and 'affects'.
The section 'Types' holds the meaning of the two shapes and of
'affects'. The field 'kind' is an open
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

A response attack entry holds 'stance' and, on a counter entry,
the 'weapon_id' that counters. It holds the forecast 'incoming': what the
strike of the attacker does to the defender under that stance. A
counter entry also holds the forecast 'counter': what the counter
does to the attacker. A stance entry reads no support unit. A
support defender changes no outcome of the stance, so each one
carries its own forecast in 'support_defenders'.

A support defense entry holds 'unit_id' and the forecast
'incoming': what the strike does to that support defender. A support
attack entry holds 'unit_id', 'weapon_id' and the forecast 'strike':
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

The 'unit_id' of the request and the 'unit_id' of the action name
one unit. A request where the two differ is a bad_request.

The field 'response_attack' is necessary for an action of the kind
'attack', because such an action always gives a list. The field is
not permitted for every other kind. A response attack inside
'action' is a bad_request: the response attack travels in the field
'response_attack' of the request.

The client names every support unit of the engagement, and the
engine names none. The action holds 'support_attacker_ids', the units
of the side of the actor that join the strike, and
'support_defender_id', the unit that takes a counter strike for the
actor. The response attack holds the same two fields for the
defending side: 'support_attacker_ids' join the answer of the
defender, and 'support_defender_id' is the unit that takes the strike
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
or counter), 'shooter_id', 'struck_id', 'weapon_id', 'landed',
'damage', and 'killed'. The value 'phase' carries 'turn' and
'phase': the engine rotated the phase after the activation, and
the section 'Turn cycle' holds the rule.

'board' is the summary: 'turn', 'phase', 'pending_ids' (the
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
illegal_action for a target that is no foe, an attack that fills
both 'weapon_id' and 'map_weapon_id' or neither, a weapon the unit
does not carry, a weapon the unit cannot pay for, a weapon that does not
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

### Identity

The engine issues every identifier, and an identifier is a
position. A unit id is the position of the unit in the unit list
of the state. A weapon id is the position of the weapon in
'weapons' of its mech. A map weapon id is the position in
'map_weapons'. Every id on the wire is an integer, and the name of
an id field ends in '_id' or '_ids'.

A client holds an id as an opaque handle. It does not interpret
the handle, it does not reorder the list that the handle indexes,
and it hands the handle back unchanged. An id is stable inside one
session and promises nothing across sessions.

The unit list is append only. The engine never deletes a unit and
never reorders the list. A destroyed unit keeps its place with no
hit points left.

A name is not an identifier. The 'name' of a weapon entry says
what the weapon is, for a person. The position says which weapon
it is, for the engine.

The engine bounds-checks every id that arrives on the wire, and it
refuses a bad id with 'illegal_action'. There is no in-band value
for "no unit": a field that can hold no id is null.

A stage definition can point at an enemy by position. The victory
entry and the enemy list travel in one 'init' payload, so its
'target_id' indexes the list beside it. The loader sends the enemy
list in the order of the definition, and the engine keeps that
order, so one definition gives the same positions in every
session.

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

A skill holds an 'AffectArea', the same pair of shapes that a map
weapon holds. The area of a skill is an arbitrary set of cells. It
takes any shape, for example the shape of the letters "ILOVEU". A
minimum range, a maximum range and a radius cannot express such a
shape, so they are the wrong description of the area and not an
incomplete one (user ruling 2026-08-31). The pair replaces them.

The name of each field matches the column that fills it:

| Field | Datamine column | Content |
|---|---|---|
| apply_shape | (no column) | The cells where the center of the skill can sit |
| effect_shape | effect_range | The cells that the skill acts on |

An empty 'apply_shape.cells' is no choice of center. The skill
opens its area at the cell of the caster, and the player picks
nothing. A set that holds cells is a choice: the player picks one
cell of the set, and the picked cell travels in the field 'aim' of
the action. A single target travels in the field 'target_id'.

The supporter ability 1001000150 of
docs/reference/datamine-samples/202608161248/supporter/ is the
caster-centered case. Its 'effect_range' is a diamond of radius four
that holds the origin (0,0), and the record holds no shooting range
of its own.

This version defines the two shapes and it gives no rule. No rule
expands a shape, turns a shape, or picks the units of the area.

The producer of a skill can leave the two shapes empty. The panel
of the game shows no cells and no heading, so the vision layer of
this repository writes an empty 'cells' and a 'direction' of 'none'
in each shape. An empty shape from this source is data that is
missing. No rule may read it as an area of no cells, and no rule
may read such an 'apply_shape' as the caster rule above.

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
- An action that fires carries exactly one of 'weapon_id' and
  'map_weapon_id'. An action of a kind that fires nothing carries
  both null.
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
and it grants no response attack. Version 1.9 gives the map weapon
its fields. It gives no rule: no rule expands a shape, turns a
shape, spends the ammunition, picks the units of the area, or
computes the damage. Issue #79 writes those rules.

'ShapeRange' is one area. It holds 'cells', a list of cell offsets
from an origin, and 'direction'. The author writes the offsets one
time, against one base heading. The direction then turns the full
set of the offsets. The rotation is a rule, and version 1.9 holds
no rule, so no code turns a shape yet.

'Direction' holds 'none', 'up', 'down', 'left' and 'right'. The
value 'none' is a shape that needs no heading, for example a shape
that is the same in every heading.

'AffectArea' is the pair of shapes of one owner. A map weapon holds
one, and a skill holds one. It is an anonymous embedded field in Go,
so its two shapes stay flat on the wire and keep their position. The
name of each field matches the column that fills it:

| Field | Datamine column | Content |
|---|---|---|
| apply_shape | map_weapon_shooting_range | The cells where the center of the strike can sit |
| effect_shape | map_weapon_effect_range | The cells that the strike hits |

An empty 'apply_shape.cells' is no choice of center. The weapon
opens its area at the cell of the caster, and the player picks
nothing. A set that holds cells is a choice: the player picks one
cell of the set, and the picked cell travels in the field 'aim' of
the action. This rule replaces the enum 'MapWeaponOrigin' of
version 1.8.

An integer cannot hold 'apply_shape', because the set has holes.
The unit 1114000250 of
docs/reference/datamine-samples/202608161248/unit/ carries a hollow
diamond: the set reaches five cells, and the cells inside radius
two are absent. A radius states a full disc, so a radius states the
wrong set.

'MapWeaponAffects' holds the faction filter of the units that the
area strikes: 'ally', 'enemy', or 'all'. It is a separate enum from
'SkillAffects', because the audience of a map weapon and the
audience of a skill are two different sets (user ruling
2026-08-31).

The field 'ammo_max' of a map weapon is the static maximum. The
field 'map_weapon_ammo' of a unit is the count that is left: one
entry for each entry of 'map_weapons' of its mech, in the same
order. The maximum belongs to the definition, and the count belongs
to the state. 'load' refuses a unit whose count list and map weapon
list differ in length.

The producer of a map weapon can leave the two shapes empty. The
panel of the game shows no cells and no heading, so the vision
layer of this repository writes an empty 'cells' and a 'direction'
of 'none' in each shape. An empty shape from this source is data
that is missing. No rule may read it as an area of no cells, and no
rule may read such an 'apply_shape' as the caster rule above.

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
| pos, size, acted, the charge counters, map_weapon_ammo, debuffs, skills | The board state, as before |
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
- A sixth exception on record: version 1.9 (2026-08-31, issue #88)
  gave the map weapon two shapes. The field 'shape' became
  'apply_shape' and it keeps its meaning. The new field
  'effect_shape' holds the cells where the center of the strike can
  sit. The enum 'MapWeaponOrigin' and the field 'center_range' are
  removed: an empty 'effect_shape' now says what 'origin' said,
  and one integer cannot hold a cell set that has holes. The user
  ruled the two names, and the two names cross over the two columns
  of the datamine. This version defines the shape and it fires no
  map weapon: no rule reads the fields. A client of version 1.8
  does not read a 1.9 map weapon.
- A seventh exception on record: version 1.10 (2026-08-31, issue
  #88) gave the skill an area. The skill of the state and the skill
  entry of 'actions' each carry the new fields 'apply_shape' and
  'effect_shape', both of the type 'ShapeRange'. They are the
  replacement of 'range_min', 'range_max' and 'blast', which version
  1.7 removed, and they are not a return of those three fields. The
  two names cross over the datamine, as they do on a map weapon. The
  same version puts the pair in the new Go type 'AffectArea', which
  the map weapon and the skill share. The wire does not move: the
  type is an anonymous embedded field, so the two keys stay flat and
  keep their position. This version gives the skill an area and it
  gives no rule: no rule reads the two fields. A client of version
  1.9 does not read a 1.10 skill.
- An eighth exception on record: version 1.11 (2026-09-01, issue #90)
  exchanged the contents of 'apply_shape' and 'effect_shape'. The two
  names stay. 'apply_shape' now holds the cells where the center of
  the area can sit, and 'effect_shape' now holds the cells that the
  owner acts on. The crossover of version 1.9 and version 1.10 ends:
  'effect_shape' carries 'map_weapon_effect_range' on a map weapon and
  'effect_range' on a skill, so the name matches the column. The
  caster rule follows its content, so an empty 'apply_shape' is the
  rule that an empty 'effect_shape' held before. The user ruled the
  exchange. This version moves no byte of any board: every shape that
  a producer writes today is empty. A client of version 1.10 reads a
  1.11 area and it reads the two shapes reversed.
- A ninth exception on record: version 2.0 (2026-09-01, issue #89)
  made the position the identity. The engine issues every id, and
  an id is the position in the list that holds the thing; the
  section 'Identity' holds the scheme. The unit payload loses
  'unit_id' and the ammunition map: the list 'map_weapon_ammo'
  stands in the place of 'ammo', one count for each map weapon, in
  the same order. The action and the response attack lose 'weapon',
  'support_defender' and 'support_attackers'; they carry
  'weapon_id', 'map_weapon_id', 'support_defender_id' and
  'support_attacker_ids', and an action that fires fills exactly
  one of the two weapon fields. The 'target_id' of an action and of
  a victory entry is a position. The answers move with the wire:
  every 'unit_id' is a position, a support attack entry carries
  'weapon_id', a strike event carries 'shooter_id', 'struck_id' and
  'weapon_id', the board summary carries 'pending_ids' in the place
  of 'pending', 'placed' of 'place' is a position list, and 'ammo'
  of a map weapon entry is an integer, never null. A weapon keeps
  its 'name' as data for a person. This is the first breaking wire
  change of the engine: a client of a 1.x version does not read a
  2.0 board.
